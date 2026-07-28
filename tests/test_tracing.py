"""Adversarial tests for the tracing layer.

These target the failure modes, not the happy path: tracing absent, no trace
active, a viewer that won't start, an empty log, and the redaction landmine
where any field name containing "token" is silently scrubbed.
"""
import pytest

import src.config as cfg
import src.tracing as tracing
from src.tracing import TRACING_AVAILABLE, active, configure_tracing, install_middleware


# ── Graceful degradation: TraceAct not installed ──────────────────────────────
# The whole point is that an observability dependency can never stop an analyst
# from working a case. Simulate absence by flipping the flag the module checks.

def test_active_returns_null_when_tracing_absent(monkeypatch):
    monkeypatch.setattr(tracing, "TRACING_AVAILABLE", False)
    assert active() is tracing._NULL


def test_configure_tracing_is_noop_when_absent(monkeypatch):
    monkeypatch.setattr(tracing, "TRACING_AVAILABLE", False)
    # Must not raise and must not touch the sink config.
    assert configure_tracing() is None


def test_install_middleware_skips_when_absent(monkeypatch):
    monkeypatch.setattr(tracing, "TRACING_AVAILABLE", False)

    class FakeApp:
        wsgi_app = "original"

    app = FakeApp()
    install_middleware(app)
    assert app.wsgi_app == "original"  # left untouched, not wrapped


# ── _NullTrace: must swallow every call, whatever it's named ───────────────────

def test_null_trace_swallows_known_methods():
    t = tracing._NULL
    # None of these may raise; all return None.
    assert t.step("validated") is None
    assert t.file(operation="read", target="x.pdf") is None
    assert t.model(operation="completion", target="gpt-5", usage_total=99) is None
    assert t.input({"a": 1}) is None
    assert t.output({"b": 2}) is None
    assert t.event(kind="db", operation="insert") is None


def test_null_trace_swallows_arbitrary_unknown_method():
    # A call site could invoke any helper the real trace exposes; the stand-in
    # must not care what it's called or what it's passed.
    t = tracing._NULL
    assert t.frobnicate() is None
    assert t.some_new_helper(1, 2, three=3, four=[4]) is None


def test_null_trace_attribute_is_always_callable():
    t = tracing._NULL
    for name in ("step", "db", "http", "touch", "set_meta", "totally_made_up"):
        assert callable(getattr(t, name))


# ── active() with tracing on but nothing running ──────────────────────────────

@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_active_returns_null_outside_a_trace():
    # No @traced_action on the stack → the no-op stand-in, never None.
    assert active() is tracing._NULL


# ── Redaction landmine: field names containing "token" get scrubbed ───────────

def _run_capture(monkeypatch, tmp_path, payload):
    """Configure real tracing to a temp log, emit one output, return it back."""
    from traceact import TraceLog
    from src.tracing import traced_action

    monkeypatch.setattr(tracing, "TRACE_FILE", tmp_path / "logs" / "traces.jsonl")
    configure_tracing()

    @traced_action(action="redact.probe", kind="app")
    def go():
        active().output(payload)

    go()
    tr = TraceLog(str(tracing.TRACE_FILE)).filter(action="redact.probe").last(1)[0]
    return tr["outputs"]


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_token_named_field_is_redacted_landmine(monkeypatch, tmp_path):
    # Documents the trap: ANY field whose name contains "token" is redacted.
    # If this ever stops being true, the usage_total workaround can be dropped.
    out = _run_capture(monkeypatch, tmp_path, {"tokens": 123})
    assert out["tokens"] == "[redacted]"


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_usage_total_survives_redaction(monkeypatch, tmp_path):
    # The name our instrumentation actually uses must reach the log intact.
    out = _run_capture(monkeypatch, tmp_path, {"usage_total": 456})
    assert out["usage_total"] == 456


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_api_key_is_redacted_but_plain_fields_survive(monkeypatch, tmp_path):
    out = _run_capture(monkeypatch, tmp_path, {"api_key": "sk-secret", "kept": "hi"})
    assert out["api_key"] == "[redacted]"
    assert out["kept"] == "hi"


# ── /api/audit-trail endpoint: every branch ───────────────────────────────────

@pytest.fixture
def client():
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def test_audit_trail_503_when_tracing_absent(client, monkeypatch):
    monkeypatch.setattr(tracing, "TRACING_AVAILABLE", False)
    r = client.get("/api/audit-trail")
    assert r.status_code == 503
    assert "not installed" in r.get_json()["error"]


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_audit_trail_404_when_no_log(client, monkeypatch, tmp_path):
    monkeypatch.setattr(tracing, "TRACE_FILE", tmp_path / "nope.jsonl")
    r = client.get("/api/audit-trail")
    assert r.status_code == 404
    assert "No traces" in r.get_json()["error"]


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_audit_trail_500_when_viewer_fails(client, monkeypatch, tmp_path):
    log = tmp_path / "traces.jsonl"
    log.write_text('{"trace_id":"t"}\n')
    monkeypatch.setattr(tracing, "TRACE_FILE", log)

    import traceact.viewer.instance as inst

    def boom(*_a, **_k):
        raise RuntimeError("viewer refused to bind")

    monkeypatch.setattr(inst, "launch_or_connect", boom)
    r = client.get("/api/audit-trail")
    assert r.status_code == 500
    assert "Could not start" in r.get_json()["error"]


def _fake_viewer(monkeypatch, tmp_path, base_path=tracing.VIEWER_BASE_PATH,
                 token="tok-secret", source="casewright"):
    """Point the tracing layer at a viewer that doesn't exist.

    Never spawn a real one in a test: it outlives the process and writes to
    the developer's own ~/.traceact state file.
    """
    log = tmp_path / "traces.jsonl"
    log.write_text('{"trace_id":"t"}\n')
    monkeypatch.setattr(tracing, "TRACE_FILE", log)

    import traceact.viewer.instance as inst
    url = f"http://127.0.0.1:8765{base_path}/?source={source}&token={token}"
    monkeypatch.setattr(inst, "launch_or_connect", lambda *_a, **_k: url)
    monkeypatch.setattr(inst, "find_running", lambda *_a, **_k: {
        "host": "127.0.0.1", "port": 8765, "base_path": base_path,
        "token": token, "health": {},
    })
    return log


@pytest.fixture(autouse=True)
def _clear_viewer_cache():
    """The resolved viewer is cached in a module global, so one test's fake
    viewer would otherwise still be live in the next."""
    tracing._viewer_target = None
    yield
    tracing._viewer_target = None


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_audit_trail_returns_same_origin_url_when_proxyable(client, monkeypatch, tmp_path):
    _fake_viewer(monkeypatch, tmp_path)
    r = client.get("/api/audit-trail")
    assert r.status_code == 200
    body = r.get_json()
    assert body["proxied"] is True
    assert body["url"] == "/audit-viewer/?source=casewright"


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_audit_trail_never_leaks_the_token_to_the_browser(client, monkeypatch, tmp_path):
    """The token is the whole security benefit — if it reaches the front end
    it's just a URL param any onlooker can reuse against the viewer's port."""
    _fake_viewer(monkeypatch, tmp_path, token="tok-secret")
    r = client.get("/api/audit-trail")
    assert "tok-secret" not in r.get_data(as_text=True)


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_audit_trail_falls_back_to_direct_url_for_a_foreign_mount(client, monkeypatch, tmp_path):
    """A viewer another app already started keeps its own mount. Proxying
    can't reach it there, so the analyst has to be sent to it directly."""
    _fake_viewer(monkeypatch, tmp_path, base_path="", source="other")
    r = client.get("/api/audit-trail")
    assert r.status_code == 200
    body = r.get_json()
    assert body["proxied"] is False
    assert body["url"].startswith("http://127.0.0.1:8765/")


# ── /audit-viewer proxy: the guards, not the happy path ───────────────────────

@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_proxy_is_closed_in_cloud_mode(client, monkeypatch, tmp_path):
    """Casewright has no auth of its own. A trace browser on a public URL
    would hand every case file to anyone holding the link."""
    _fake_viewer(monkeypatch, tmp_path)
    monkeypatch.setattr(cfg, "get_deployment_mode", lambda: "cloud")
    for path in ("/audit-viewer/", "/audit-viewer/api/sources",
                 "/audit-viewer/api/export?source=casewright"):
        assert client.get(path).status_code == 404, path


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_proxy_503_when_no_viewer_running(client, monkeypatch):
    import traceact.viewer.instance as inst
    monkeypatch.setattr(inst, "find_running", lambda *_a, **_k: None)
    r = client.get("/audit-viewer/api/sources")
    assert r.status_code == 503


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_proxy_503_rather_than_forwarding_to_a_foreign_mount(client, monkeypatch, tmp_path):
    """Forwarding to a viewer mounted elsewhere would serve a page whose JS
    calls back to paths this proxy doesn't own — a broken viewer, not a
    working one. Refuse instead."""
    _fake_viewer(monkeypatch, tmp_path, base_path="/somewhere-else")
    r = client.get("/audit-viewer/api/sources")
    assert r.status_code == 503


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_proxy_injects_the_token_upstream(client, monkeypatch, tmp_path):
    """Without the header the tokened viewer answers 403 to everything."""
    _fake_viewer(monkeypatch, tmp_path, token="tok-secret")
    seen = {}

    class _Resp:
        status = 200
        headers = {"Content-Type": "application/json"}

        def read1(self, _n):
            return b""

        def close(self):
            pass

    def fake_urlopen(req, **_kw):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.headers)
        return _Resp()

    monkeypatch.setattr("app.urllib.request.urlopen", fake_urlopen)
    client.get("/audit-viewer/api/sources?source=casewright")

    # urllib title-cases header names on the way in.
    assert seen["headers"].get("X-traceact-token") == "tok-secret"
    assert seen["url"] == (
        "http://127.0.0.1:8765/audit-viewer/api/sources?source=casewright"
    )


@pytest.mark.skipif(not TRACING_AVAILABLE, reason="requires traceact")
def test_launch_viewer_raises_when_the_viewer_never_answers(monkeypatch, tmp_path):
    log = tmp_path / "traces.jsonl"
    log.write_text('{"trace_id":"t"}\n')
    monkeypatch.setattr(tracing, "TRACE_FILE", log)

    import traceact.viewer.instance as inst
    monkeypatch.setattr(inst, "launch_or_connect", lambda *_a, **_k: "http://127.0.0.1:8765/")
    monkeypatch.setattr(inst, "find_running", lambda *_a, **_k: None)

    with pytest.raises(RuntimeError):
        tracing.launch_viewer()
