import io
import json
import os
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from src import config as cfg
from src.logger import log_event
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

app = Flask(__name__)

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


def _run_analysis(case_id: str) -> tuple[dict, int]:
    settings = cfg.get_raw_settings()
    case = get_case(case_id)
    if not case:
        raise ValueError(f"Case {case_id} not found.")

    rule = get_rule(case["scheme"], case["reason_code"])
    docs_dir = settings["documents_dir"]
    extracted = extract_case_documents(case.get("merchant_evidence_documents", []), docs_dir)

    system_prompt, text_prompt, image_parts = build_prompt(case, rule, extracted)
    workup, tokens = call_llm(system_prompt, text_prompt, image_parts, settings)

    valid, errors = validate_workup(workup)

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


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(cfg.get_settings())


@app.route("/api/settings/test", methods=["POST"])
def test_settings():
    body = request.get_json(force=True)
    provider = (body.get("provider") or "").lower().strip()
    api_key = (body.get("api_key") or "").strip()

    # Fall back to the saved key if the caller didn't supply one
    if not api_key:
        raw = cfg.get_raw_settings()
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
        msg = getattr(e, "message", None) or str(e)
        if not isinstance(msg, str):
            msg = str(msg)
        log_event("key_test", {"provider": provider, "valid": False, "error": msg[:200]}, level="warn")
        return jsonify({"valid": False, "error": msg})


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
        raw = cfg.get_raw_settings()
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
        workup, tokens = _run_analysis(case_id)
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
        return jsonify({"error": f"Analysis failed: {e}"}), 500
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
