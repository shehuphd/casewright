import json
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).parent.parent
WORKUPS_DIR = BASE_DIR / "outputs" / "workups"


def _path(case_id: str) -> Path:
    return WORKUPS_DIR / f"{case_id}.json"


def workup_exists(case_id: str) -> bool:
    return _path(case_id).exists()


def load_workup(case_id: str) -> dict | None:
    p = _path(case_id)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def save_workup(case_id: str, workup: dict) -> None:
    WORKUPS_DIR.mkdir(parents=True, exist_ok=True)
    with open(_path(case_id), "w") as f:
        json.dump(workup, f, indent=2)


def delete_workup(case_id: str) -> bool:
    p = _path(case_id)
    if p.exists():
        p.unlink()
        return True
    return False


def clear_all_workups() -> int:
    count = 0
    for p in WORKUPS_DIR.glob("*.json"):
        p.unlink()
        count += 1
    return count


def save_override(case_id: str, action: str, notes: str) -> dict | None:
    workup = load_workup(case_id)
    if workup is None:
        return None
    workup["analyst_override"] = {
        "action": action,
        "notes": notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    save_workup(case_id, workup)
    return workup


def save_rationale(case_id: str, text: str) -> dict | None:
    workup = load_workup(case_id)
    if workup is None:
        return None
    workup["representment_rationale"] = text
    save_workup(case_id, workup)
    return workup
