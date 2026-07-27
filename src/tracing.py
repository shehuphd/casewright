"""TraceAct configuration and helpers.

Casewright's recommendations have to be auditable, so every analysis run is
traced: which documents were read, what was sent to the model, how long each
step took, and what came back.
"""
from pathlib import Path

from traceact import JsonlSink, TraceBudget, TraceConfig, configure
from traceact.trace import get_active_trace

BASE_DIR = Path(__file__).parent.parent
TRACE_FILE = BASE_DIR / "logs" / "traces.jsonl"


class _NullTrace:
    """Stands in when no trace is active so call sites don't need guards."""

    def __getattr__(self, _name):
        def _noop(*_args, **_kwargs):
            return None
        return _noop


_NULL = _NullTrace()


def configure_tracing() -> None:
    """Set up TraceAct. Call once at startup, before any traced code runs."""
    TRACE_FILE.parent.mkdir(exist_ok=True)
    configure(
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


def active():
    """The current trace, or a no-op stand-in when tracing isn't running."""
    return get_active_trace() or _NULL
