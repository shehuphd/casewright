import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def isolate_tracing(tmp_path):
    """Keep traces out of the real log; restore defaults after each test."""
    from traceact import JsonlSink, configure, reset_config
    configure(sinks=[JsonlSink(str(tmp_path / "traces.jsonl"))])
    yield
    reset_config()
