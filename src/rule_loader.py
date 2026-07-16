import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
RULES_FILE = BASE_DIR / "data" / "reason_codes.json"

_rules: dict | None = None


def _load() -> dict:
    global _rules
    if _rules is None:
        with open(RULES_FILE) as f:
            _rules = json.load(f)
    return _rules


def get_rule(scheme: str, reason_code: str) -> dict | None:
    rules = _load()
    scheme_key = scheme.lower()
    return rules.get(scheme_key, {}).get(str(reason_code))


def format_rule_text(rule: dict) -> str:
    """Produce a human-readable description of a rule for inclusion in the LLM prompt."""
    if not rule:
        return "No matching rule found."

    lines = [
        f"{rule.get('scheme', '').title()} {rule.get('code', '')} — {rule.get('label', '')}",
        f"Issuer claim: {rule.get('issuer_claim', '')}",
    ]

    if rule.get("non_representable"):
        lines.append(f"\nNON-REPRESENTABLE: {rule.get('non_representable_note', '')}")
        lines.append("Default recommendation: accept_liability")
        return "\n".join(lines)

    logic = rule.get("logic", "ALL")
    logic_labels = {
        "ALL": "ALL of the following are required",
        "ANY_TWO": "ANY TWO of the following are sufficient",
        "ANY_ONE": "ANY ONE of the following is sufficient",
        "EITHER": "EITHER of the following is sufficient",
    }
    lines.append(f"\nLogic: {logic_labels.get(logic, logic)}")
    lines.append("Requirements:")
    for i, req in enumerate(rule.get("requirements", []), 1):
        lines.append(f"  {i}. {req}")

    return "\n".join(lines)
