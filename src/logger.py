import json
from datetime import datetime, timezone
from pathlib import Path

_LOGS_DIR = Path(__file__).parent.parent / "logs"
_LOG_FILE = _LOGS_DIR / "casewright.jsonl"


def log_event(event: str, data: dict | None = None, level: str = "info") -> None:
    _LOGS_DIR.mkdir(exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        "data": data or {},
    }
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
