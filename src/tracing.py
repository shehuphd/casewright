"""TraceAct configuration and helpers.

Casewright's recommendations have to be auditable, so every analysis run is
traced: which documents were read, what was sent to the model, how long each
step took, and what came back.

Tracing is optional. If TraceAct isn't installed the app still runs with every
tracing call becoming a no-op, so an observability dependency can never stop an
analyst from working a case.
"""
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
TRACE_FILE = BASE_DIR / "logs" / "traces.jsonl"

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
