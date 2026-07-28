"""TraceAct configuration and helpers.

Casewright's recommendations have to be auditable, so every analysis run is
traced: which documents were read, what was sent to the model, how long each
step took, and what came back.

Tracing is optional. If TraceAct isn't installed the app still runs with every
tracing call becoming a no-op, so an observability dependency can never stop an
analyst from working a case.
"""
import threading
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
TRACE_FILE = BASE_DIR / "logs" / "traces.jsonl"

# The viewer is mounted under this prefix so it can be reverse-proxied onto
# Casewright's own port instead of sending the analyst to a second one.
VIEWER_BASE_PATH = "/audit-viewer"

_viewer_lock = threading.Lock()
_viewer_target = None

try:
    from traceact import (
        JsonlSink,
        TraceActMiddleware,
        TraceBudget,
        TraceConfig,
        configure,
        traced_action,
    )
    from traceact.trace import get_active_trace
    TRACING_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the package
    TRACING_AVAILABLE = False

    def traced_action(*_args, **_kwargs):
        """Passthrough stand-in for the real decorator."""
        def decorator(fn):
            return fn
        return decorator


class _NullTrace:
    """Stands in when no trace is active so call sites don't need guards."""

    def __getattr__(self, _name):
        def _noop(*_args, **_kwargs):
            return None
        return _noop


_NULL = _NullTrace()


def configure_tracing() -> None:
    """Set up TraceAct. Call once at startup, before any traced code runs."""
    if not TRACING_AVAILABLE:
        return
    TRACE_FILE.parent.mkdir(exist_ok=True)
    configure(
        project="casewright",
        config=TraceConfig(
            enabled=True,
            sink_mode="blocking",
            capture_inputs=False,
            capture_outputs=True,
            # api_keys broadens the baseline redaction; document paths are left
            # readable because knowing which file was read is the audit trail.
            redaction_presets=["api_keys"],
        ),
        budget=TraceBudget(
            max_events=200,
            max_steps=100,
            sample_rate=1.0,
            always_trace_errors=True,
        ),
        sinks=[JsonlSink(str(TRACE_FILE), max_bytes=50_000_000)],
    )


def install_middleware(flask_app) -> None:
    """Wrap the WSGI app so inbound trace headers propagate."""
    if TRACING_AVAILABLE:
        flask_app.wsgi_app = TraceActMiddleware(flask_app.wsgi_app)


def active():
    """The current trace, or a no-op stand-in when tracing isn't running."""
    if not TRACING_AVAILABLE:
        return _NULL
    return get_active_trace() or _NULL


def launch_viewer() -> dict:
    """Start or reuse the TraceAct viewer and return where it can be reached.

    The returned dict is ``{host, port, base_path, token, source}``.

    Token auth is always requested. The token stays in this process and is
    injected by the proxy, so the browser never carries it and no other OS
    user on the machine can read case traces off the viewer's port.

    A viewer another app already started is reused as it stands, mount and
    token included, so the returned ``base_path`` may not be the one asked
    for. Callers compare it against ``VIEWER_BASE_PATH`` to know whether they
    can proxy it or have to send the analyst to the viewer's own URL.
    """
    global _viewer_target
    from urllib.parse import parse_qs, urlparse

    from traceact.viewer.instance import find_running, launch_or_connect

    with _viewer_lock:
        url = launch_or_connect(
            source=str(TRACE_FILE),
            name="casewright",
            base_path=VIEWER_BASE_PATH,
            require_token=True,
        )
        running = find_running()
        if running is None:
            raise RuntimeError("the viewer did not answer after starting")
        # The name the viewer actually registered wins: it dedupes by path, so
        # a log already added under another name keeps that one.
        source = parse_qs(urlparse(url).query).get("source", [""])[0]
        _viewer_target = {
            "host": running["host"],
            "port": running["port"],
            "base_path": running["base_path"],
            "token": running["token"],
            "source": source,
            "url": url,
        }
        return _viewer_target


def viewer_target():
    """The running viewer's location, or None if it isn't up.

    Cached from :func:`launch_viewer`, then re-derived from TraceAct's state
    file so a proxied request still resolves after a Casewright restart.
    """
    global _viewer_target
    if not TRACING_AVAILABLE:
        return None
    if _viewer_target is not None:
        return _viewer_target
    from traceact.viewer.instance import find_running

    with _viewer_lock:
        if _viewer_target is None:
            running = find_running()
            if running is not None:
                _viewer_target = {**running, "source": "", "url": ""}
        return _viewer_target
