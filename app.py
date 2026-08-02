import io
import json
import os
import threading
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context

from src import config as cfg
from src import tracing
from src.logger import log_event
from src.tracing import active, configure_tracing, install_middleware, traced_action
from src.analysis_store import (
    clear_all_workups,
    load_workup,
    save_override,
    save_rationale,
    save_workup,
    workup_exists,
)
from src.data_loader import get_case, load_cases
from src.document_extractor import extract_case_documents
from src.llm_client import call_llm
from src.prompt_builder import build_prompt
from src.rule_loader import get_rule
from src.schema import validate_workup

configure_tracing()

app = Flask(__name__)
install_middleware(app)

_running: set[str] = set()
_running_lock = threading.Lock()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_amount(amount: dict) -> str:
    symbols = {"GBP": "£", "EUR": "€", "USD": "$"}
    sym = symbols.get(amount.get("currency", ""), "")
    return f"{sym}{amount.get('value', 0):,.2f}"


def _case_summary(case: dict) -> dict:
    workup = load_workup(case["case_id"])
    ov = (workup or {}).get("analyst_override") or {}
    ov_action = ov.get("action")
    effective_action = (
        ov_action if (ov_action and ov_action != "keep")
        else (workup.get("recommended_action") if workup else None)
    )
    return {
        "case_id": case["case_id"],
        "scheme": case["scheme"],
        "reason_code": case["reason_code"],
        "reason_code_label": case["reason_code_label"],
        "merchant_name": case["transaction"]["merchant_name"],
        "chargeback_amount": case["chargeback_amount"],
        "amount_display": _fmt_amount(case["chargeback_amount"]),
        "chargeback_date": case["chargeback_date"],
        "evidence_count": len(case.get("merchant_evidence_documents", [])),
        "workup_status": "processed" if workup else "unprocessed",
        "recommended_action": effective_action,
        "confidence": workup.get("confidence") if workup else None,
    }


@traced_action(action="case.analyse", kind="app", actor="user", project="casewright")
def _caller_settings() -> dict:
    """Resolve credentials for this request.

    In cloud mode the analyst's own key rides in on headers rather than being
    read from the server's environment. Headers rather than the JSON body so
    every endpoint resolves credentials the same way, whether or not it takes
    a body.
    """
    return cfg.resolve_settings({
        "provider": request.headers.get("X-LLM-Provider"),
        "api_key": request.headers.get("X-LLM-Key"),
        "text_model": request.headers.get("X-LLM-Text-Model"),
        "vision_model": request.headers.get("X-LLM-Vision-Model"),
    })


def _run_analysis(case_id: str, settings: dict) -> tuple[dict, int]:
    trace = active()
    case = get_case(case_id)
    if not case:
        raise ValueError(f"Case {case_id} not found.")

    trace.input({
        "case_id": case_id,
        "scheme": case["scheme"],
        "reason_code": case["reason_code"],
        "provider": settings["provider"],
        "model": settings["text_model"],
    })

    rule = get_rule(case["scheme"], case["reason_code"])
    trace.step(
        f"Loaded rule for {case['scheme']} {case['reason_code']}" if rule
        else f"No rule found for {case['scheme']} {case['reason_code']}"
    )

    docs_dir = settings["documents_dir"]
    extracted = extract_case_documents(case.get("merchant_evidence_documents", []), docs_dir)
    trace.step(f"Extracted {len(extracted)} evidence document(s)")

    system_prompt, text_prompt, image_parts = build_prompt(case, rule, extracted)
    trace.step(f"Built prompt ({len(text_prompt):,} chars, {len(image_parts)} image(s))")

    workup, tokens = call_llm(system_prompt, text_prompt, image_parts, settings)

    valid, errors = validate_workup(workup)
    trace.step("Schema validation passed" if valid else f"Schema validation failed: {len(errors)} error(s)")

    limitations = []
    for doc in extracted:
        if doc.get("status") == "not_found":
            limitations.append(f"{doc['filename']}: file not found in documents directory.")
        elif doc.get("status") == "needs_review":
            limitations.append(f"{doc['filename']}: text extraction failed or returned empty.")

    workup["processing_notes"] = {
        "model_used": settings["text_model"],
        "provider": settings["provider"],
        "documents_processed": [d["filename"] for d in extracted],
        "extraction_method": "pypdf (PDF) / base64 vision (images)",
        "token_estimate": tokens,
        "output_json_valid": valid,
        "validation_errors": errors,
        "limitations": limitations,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    workup["evidence_files"] = [
        {
            "filename": d["filename"],
            "file_type": d.get("file_type", "unknown"),
            "extraction_status": d.get("status", "unknown"),
            "page_count": d.get("page_count"),
        }
        for d in extracted
    ]

    if "analyst_override" not in workup:
        workup["analyst_override"] = {"action": "keep", "notes": "", "timestamp": None}

    save_workup(case_id, workup)
    trace.file(operation="write", target=f"outputs/workups/{case_id}.json")
    trace.output({
        "recommended_action": workup.get("recommended_action"),
        "confidence": workup.get("confidence"),
        "output_json_valid": valid,
        "usage_total": tokens,  # see llm_client: "token" in a field name is redacted
    })
    return workup, tokens


def _fetch_filtered_models(provider: str, api_key: str) -> list[str]:
    import re

    _OPENAI_EXCLUDE = frozenset({
        "embedding", "realtime", "tts", "whisper", "dall-e",
        "audio", "moderation", "transcrib", "image", "search",
    })

    if provider == "openai":
        from openai import OpenAI
        raw = OpenAI(api_key=api_key).models.list()
        ids = [m.id for m in raw.data
               if re.match(r"^(gpt-|o\d|chatgpt-)", m.id)
               and not any(kw in m.id for kw in _OPENAI_EXCLUDE)]
    elif provider == "anthropic":
        from anthropic import Anthropic
        raw = Anthropic(api_key=api_key).models.list()
        ids = [m.id for m in raw.data if m.id.startswith("claude-")]
    else:
        return []

    def _first_int(model_id: str) -> int:
        m = re.search(r"\d+", model_id)
        return int(m.group()) if m else 0

    groups: dict[int, list[str]] = {}
    for mid in ids:
        groups.setdefault(_first_int(mid), []).append(mid)

    top2 = sorted(groups, reverse=True)[:2]
    result = []
    for v in top2:
        result.extend(sorted(groups[v]))
    return result


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/onboarding", methods=["GET"])
def onboarding_status():
    raw = cfg.get_raw_settings()
    mode = cfg.get_deployment_mode()
    # key_configured describes the server's own .env, which only exists in a
    # local run. Reporting it in cloud mode was the source of a wrong signal:
    # a developer's local .env lit up "API key detected" on the cloud card,
    # describing their own machine rather than the deployment. Cloud is
    # bring-your-own-key, so there is nothing on the server to detect.
    return jsonify({
        "deployment_mode": mode,
        "key_configured": bool(raw.get("api_key")) if mode != "cloud" else False,
        "provider": (raw.get("provider") or None) if mode != "cloud" else None,
        "env_exists": cfg.env_file_exists(),
    })


@app.route("/api/traces/download", methods=["GET"])
def download_traces():
    from src.tracing import TRACE_FILE, TRACING_AVAILABLE
    # Closed in the cloud demo, which has no authentication: the trace log
    # carries case data, so anyone with the URL would otherwise be able to
    # pull it. A production deployment with auth in front can drop this.
    if cfg.get_deployment_mode() == "cloud":
        return jsonify({"error": "Trace download is available in local mode only."}), 403
    if not TRACING_AVAILABLE:
        return jsonify({"error": "Tracing not installed."}), 503
    if not TRACE_FILE.exists():
        return jsonify({"error": "No traces recorded yet. Run an analysis first."}), 404
    return send_file(str(TRACE_FILE), as_attachment=True, download_name="casewright-traces.jsonl")


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(cfg.get_settings())


def _friendly_provider_error(e: Exception) -> str:
    """Translate an OpenAI/Anthropic SDK exception into a message worth
    showing an analyst. The raw exception text includes the provider's own
    redacted-key rendering (a run of 60+ asterisks) and a Python dict repr of
    the error body — accurate, but unreadable in a small error box. Matched
    by exception class rather than status code parsing, since both SDKs
    already classify these consistently.
    """
    import openai
    import anthropic

    if isinstance(e, (openai.AuthenticationError, anthropic.AuthenticationError)):
        return "That API key was rejected by the provider. Double-check it's correct and try again."
    if isinstance(e, (openai.PermissionDeniedError, anthropic.PermissionDeniedError)):
        return "This key doesn't have permission to do that. Check its access on the provider's dashboard."
    if isinstance(e, (openai.RateLimitError, anthropic.RateLimitError)):
        return "The provider is rate-limiting this key right now. Wait a moment and try again."
    if isinstance(e, anthropic.OverloadedError):
        return "The provider is overloaded right now. Try again in a moment."
    if isinstance(e, (openai.APIConnectionError, anthropic.APIConnectionError,
                      openai.APITimeoutError, anthropic.APITimeoutError)):
        return "Could not reach the provider. Check your connection and try again."
    if isinstance(e, (openai.InternalServerError, anthropic.InternalServerError)):
        return "The provider is having issues right now. Try again in a moment."
    return "Could not verify this key. Try again, or check the provider's status page."


@app.route("/api/settings/test", methods=["POST"])
def test_settings():
    body = request.get_json(force=True)
    provider = (body.get("provider") or "").lower().strip()
    api_key = (body.get("api_key") or "").strip()

    # Fall back to the saved key if the caller didn't supply one
    if not api_key:
        # resolve_settings, not get_raw_settings: in cloud mode there is no
        # server-side key to fall back to, and reaching for one would let a
        # keyless caller spend the operator's credit.
        raw = cfg.resolve_settings()
        api_key = raw.get("api_key", "")
        if not provider:
            provider = raw.get("provider", "")

    if not api_key:
        return jsonify({"valid": False, "error": "No API key to test."})

    try:
        if provider == "openai":
            from openai import OpenAI
            OpenAI(api_key=api_key).models.list()
        elif provider == "anthropic":
            from anthropic import Anthropic
            Anthropic(api_key=api_key).models.list()
        else:
            return jsonify({"valid": False, "error": f"Unknown provider '{provider}'."})
        log_event("key_test", {"provider": provider, "valid": True})
        return jsonify({"valid": True})
    except Exception as e:
        # The raw message is logged in full for debugging; the analyst only
        # ever sees the translated version.
        raw_msg = getattr(e, "message", None) or str(e)
        if not isinstance(raw_msg, str):
            raw_msg = str(raw_msg)
        log_event("key_test", {"provider": provider, "valid": False, "error": raw_msg[:200]}, level="warn")
        return jsonify({"valid": False, "error": _friendly_provider_error(e)})


@app.route("/api/settings/key", methods=["DELETE"])
def delete_api_key():
    cfg.delete_api_key()
    log_event("key_delete", {})
    return jsonify(cfg.get_settings())


@app.route("/api/settings", methods=["POST"])
def post_settings():
    body = request.get_json(force=True)
    cfg.save_settings(
        provider=body.get("provider", ""),
        api_key=body.get("api_key", ""),
        text_model=body.get("text_model", ""),
        vision_model=body.get("vision_model", ""),
    )
    s = cfg.get_settings()
    log_event("settings_save", {"provider": s.get("provider"), "text_model": s.get("text_model")})
    return jsonify(s)


@app.route("/api/settings/models", methods=["POST"])
def list_models():
    body = request.get_json(force=True)
    provider = (body.get("provider") or "").lower().strip()
    api_key = (body.get("api_key") or "").strip()

    if not api_key:
        # resolve_settings, not get_raw_settings: in cloud mode there is no
        # server-side key to fall back to, and reaching for one would let a
        # keyless caller spend the operator's credit.
        raw = cfg.resolve_settings()
        api_key = raw.get("api_key", "")
        if not provider:
            provider = raw.get("provider", "")

    if not api_key:
        return jsonify({"models": [], "error": "No API key configured."})

    try:
        models = _fetch_filtered_models(provider, api_key)
        log_event("model_list_fetch", {"provider": provider, "count": len(models)})
        return jsonify({"models": models})
    except Exception as e:
        msg = str(e)
        log_event("model_list_fetch", {"provider": provider, "error": msg[:200]}, level="error")
        return jsonify({"models": [], "error": msg}), 500


@app.route("/api/cases", methods=["GET"])
def list_cases():
    cases, errors = load_cases()
    summaries = [_case_summary(c) for c in cases]
    return jsonify({"cases": summaries, "validation_errors": errors})


@app.route("/api/cases/<case_id>", methods=["GET"])
def get_case_detail(case_id):
    case = get_case(case_id)
    if not case:
        return jsonify({"error": f"Case {case_id} not found."}), 404

    rule = get_rule(case["scheme"], case["reason_code"])
    workup = load_workup(case_id)

    return jsonify({
        "case": case,
        "rule": rule,
        "workup": workup,
        "amount_display": _fmt_amount(case["chargeback_amount"]),
    })


@app.route("/api/audit-trail", methods=["GET"])
def launch_audit_trail():
    """Open the TraceAct viewer on this instance's trace log."""
    from src.tracing import TRACE_FILE, TRACING_AVAILABLE
    if not TRACING_AVAILABLE:
        return jsonify({
            "error": "Tracing is not installed. Run: pip install -r requirements.txt"
        }), 503
    if not TRACE_FILE.exists():
        return jsonify({"error": "No traces recorded yet. Run an analysis first."}), 404
    try:
        target = tracing.launch_viewer()
    except Exception as e:
        log_event("audit_trail_error", {"error": str(e)}, level="error")
        return jsonify({"error": f"Could not start the trace viewer: {e}"}), 500

    # Normally the viewer comes up on our mount and the analyst stays on this
    # origin. A viewer another app already started keeps its own mount, and no
    # amount of proxying can reach it there, so send them to it directly.
    if target["base_path"] == tracing.VIEWER_BASE_PATH:
        url = tracing.VIEWER_BASE_PATH + "/"
        if target["source"]:
            url += "?source=" + quote(target["source"], safe="")
        proxied = True
    else:
        url = target["url"]
        proxied = False
    log_event("audit_trail_open", {"proxied": proxied})
    return jsonify({"url": url, "proxied": proxied})


# Headers that describe one hop and must not be copied onto the next.
_HOP_BY_HOP = {
    "connection", "keep-alive", "transfer-encoding", "te", "trailer",
    "upgrade", "proxy-authorization", "proxy-authenticate",
    "content-encoding", "content-length", "host",
}


@app.route("/audit-viewer/", defaults={"subpath": ""}, methods=["GET", "POST"])
@app.route("/audit-viewer/<path:subpath>", methods=["GET", "POST"])
def audit_viewer_proxy(subpath):
    """Reverse-proxy the TraceAct viewer onto Casewright's own port.

    The viewer's token is injected here and never reaches the browser, which
    is the point of running it token-gated: another OS user who can reach the
    viewer's localhost port still can't read case traces through it.

    Local deployments only. In the cloud there's no viewer process to proxy,
    and Casewright has no authentication of its own, so mounting a full trace
    browser on a public URL would hand every case file to anyone holding the
    link. Cloud analysts download the trace log instead.
    """
    if cfg.get_deployment_mode() == "cloud":
        return jsonify({"error": "The trace viewer is local-only."}), 404

    target = tracing.viewer_target()
    if target is None or target["base_path"] != tracing.VIEWER_BASE_PATH:
        return jsonify({"error": "The trace viewer is not running."}), 503

    url = f"http://{target['host']}:{target['port']}{tracing.VIEWER_BASE_PATH}/{subpath}"
    if request.query_string:
        url += "?" + request.query_string.decode("utf-8")

    headers = {"X-TraceAct-Token": target["token"]} if target["token"] else {}
    if request.headers.get("Accept"):
        headers["Accept"] = request.headers["Accept"]
    body = None
    if request.method == "POST":
        body = request.get_data()
        headers["Content-Type"] = request.headers.get("Content-Type", "application/json")

    req = urllib.request.Request(url, data=body, headers=headers, method=request.method)
    try:
        upstream = urllib.request.urlopen(req, timeout=None)
    except urllib.error.HTTPError as e:
        return Response(e.read(), status=e.code,
                        content_type=e.headers.get("Content-Type", "text/plain"))
    except Exception as e:
        return jsonify({"error": f"Could not reach the trace viewer: {e}"}), 502

    def relay():
        # read1() rather than read(): read() blocks until it has the full 8 KiB
        # or the connection closes, and the SSE tail is a long-lived stream of
        # small messages that never closes, so every event would sit here until
        # enough of them piled up to fill a buffer.
        try:
            while True:
                chunk = upstream.read1(8192)
                if not chunk:
                    break
                yield chunk
        finally:
            upstream.close()

    passthrough = [(k, v) for k, v in upstream.headers.items()
                   if k.lower() not in _HOP_BY_HOP]
    return Response(stream_with_context(relay()), status=upstream.status,
                    headers=passthrough)


@app.route("/api/analyses/running", methods=["GET"])
def get_running():
    with _running_lock:
        return jsonify({"running": list(_running)})


@app.route("/api/cases/<case_id>/analyze", methods=["POST"])
def analyze_case(case_id):
    with _running_lock:
        _running.add(case_id)
    log_event("analysis_start", {"case_id": case_id})
    try:
        workup, tokens = _run_analysis(case_id, _caller_settings())
        log_event("analysis_complete", {
            "case_id": case_id,
            "action": workup.get("recommended_action"),
            "confidence": workup.get("confidence"),
            "tokens": tokens,
        })
        return jsonify({"workup": workup})
    except ValueError as e:
        log_event("analysis_error", {"case_id": case_id, "error": str(e)}, level="warn")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        log_event("analysis_error", {"case_id": case_id, "error": str(e)}, level="error")
        return jsonify({"error": "An unexpected error occurred. Check the server logs for details."}), 500
    finally:
        with _running_lock:
            _running.discard(case_id)


@app.route("/api/cases/<case_id>/override", methods=["PATCH"])
def patch_override(case_id):
    body = request.get_json(force=True)
    action = body.get("action", "keep")
    workup = save_override(case_id, action, body.get("notes", ""))
    if workup is None:
        return jsonify({"error": "No workup found for this case. Run analysis first."}), 404
    log_event("override_save", {"case_id": case_id, "action": action})
    return jsonify({"workup": workup})


@app.route("/api/cases/<case_id>/rationale", methods=["PATCH"])
def patch_rationale(case_id):
    body = request.get_json(force=True)
    workup = save_rationale(case_id, body.get("text", ""))
    if workup is None:
        return jsonify({"error": "No workup found for this case. Run analysis first."}), 404
    return jsonify({"ok": True})


@app.route("/api/workups", methods=["DELETE"])
def delete_workups():
    count = clear_all_workups()
    log_event("workups_cleared", {"count": count})
    return jsonify({"cleared": count})


@app.route("/api/cases/<case_id>/export", methods=["GET"])
def export_case(case_id):
    case = get_case(case_id)
    if not case:
        return jsonify({"error": "Case not found."}), 404
    workup = load_workup(case_id)
    if not workup:
        return jsonify({"error": "No workup found. Run analysis first."}), 404
    log_event("export", {"case_id": case_id})

    settings = cfg.get_raw_settings()
    docs_dir = Path(settings["documents_dir"])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{case_id}_workup.json", json.dumps(workup, indent=2))

        rationale = workup.get("representment_rationale", "")
        action = workup.get("recommended_action", "")
        override = workup.get("analyst_override", {})
        final_action = override.get("action", "keep")
        effective = final_action if final_action != "keep" else action

        letter = (
            f"REPRESENTMENT RATIONALE — {case_id}\n"
            f"Merchant: {case['transaction']['merchant_name']}\n"
            f"Recommended action: {effective}\n"
            f"Chargeback amount: {_fmt_amount(case['chargeback_amount'])}\n"
            f"Chargeback date: {case['chargeback_date']}\n\n"
            f"{rationale}\n"
        )
        if override.get("notes"):
            letter += f"\nAnalyst notes: {override['notes']}\n"

        zf.writestr(f"{case_id}_rationale.txt", letter)

        for doc_name in case.get("merchant_evidence_documents", []):
            doc_path = docs_dir / doc_name
            if doc_path.exists():
                zf.write(doc_path, doc_name)

    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{case_id}_representment.zip",
    )


@app.route("/api/rules")
def view_rules():
    import re
    from flask import Response
    md = (Path(__file__).parent / "data" / "reason_codes.md").read_text(encoding="utf-8")

    def _anchor(scheme: str, code: str) -> str:
        return f"{scheme.lower()}-{code.replace('.', '-')}"

    parts = []
    for line in md.splitlines():
        m = re.match(r"^### (\w+) ([\d.]+)\s*[—–-]\s*(.+)", line)
        if m:
            a = _anchor(m.group(1), m.group(2))
            parts.append(f'<h3 id="{a}">{m.group(1)} {m.group(2)} — {m.group(3)}</h3>')
            continue
        if line.startswith("## "):
            parts.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            parts.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("> "):
            parts.append(f"<blockquote>{line[2:]}</blockquote>")
        elif line.startswith("---"):
            parts.append("<hr>")
        elif re.match(r"^\d+\. ", line):
            parts.append(f"<li>{line[line.index(' ')+1:]}</li>")
        elif line.strip():
            rendered = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            parts.append(f"<p>{rendered}</p>")

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Chargeback Reason Codes</title><style>"
        "body{max-width:820px;margin:48px auto;font-family:system-ui,sans-serif;"
        "line-height:1.65;padding:0 24px;color:#1a1a1a;font-size:15px}"
        "h1,h2,h3{color:#111;font-family:system-ui}"
        "h2{margin-top:2.5em;padding-top:1em;border-top:2px solid #e5e7eb}"
        "h3{margin-top:2em;color:#1d4ed8}"
        "blockquote{color:#6b7280;border-left:3px solid #d1d5db;margin:0 0 1em;padding-left:1em}"
        "li{margin:.3em 0}hr{border:none;border-top:1px solid #e5e7eb;margin:1.5em 0}"
        "p strong{font-weight:700}"
        "</style></head><body>"
        + "".join(parts)
        + "</body></html>"
    )
    return Response(html, mimetype="text/html")


@app.route("/api/documents/<path:filename>")
def serve_document(filename):
    settings = cfg.get_raw_settings()
    docs_dir = Path(settings["documents_dir"]).resolve()
    filepath = (docs_dir / filename).resolve()
    try:
        filepath.relative_to(docs_dir)
    except ValueError:
        return jsonify({"error": "Access denied."}), 403
    if not filepath.is_file():
        return jsonify({"error": "File not found."}), 404
    log_event("document_download", {"filename": filename})
    return send_file(str(filepath), as_attachment=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=True, port=port)
