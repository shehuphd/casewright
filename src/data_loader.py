import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CASES_FILE = BASE_DIR / "data" / "cases.json"

REQUIRED_FIELDS = [
    "case_id", "scheme", "reason_code", "reason_code_label",
    "chargeback_date", "chargeback_amount", "transaction",
    "issuer_narrative", "merchant_evidence_documents",
]


def load_cases() -> tuple[list[dict], list[dict]]:
    """Returns (valid_cases, validation_errors)."""
    with open(CASES_FILE) as f:
        raw = json.load(f)

    valid, errors = [], []
    for case in raw:
        missing = [f for f in REQUIRED_FIELDS if f not in case]
        if missing:
            errors.append({"case_id": case.get("case_id", "unknown"), "missing_fields": missing})
        else:
            valid.append(case)
    return valid, errors


def get_case(case_id: str) -> dict | None:
    cases, _ = load_cases()
    return next((c for c in cases if c["case_id"] == case_id), None)
