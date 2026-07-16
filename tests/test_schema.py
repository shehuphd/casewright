from src.schema import validate_workup, VALID_ACTIONS

_VALID = {
    "case_id": "CB-2025-TEST",
    "reason_code_summary": {"issuer_allegation": "Fraud", "scheme_requirement_summary": "Requires proof of auth."},
    "evidence_assessment": [
        {"requirement": "req1", "status": "satisfied", "supporting_document": "doc.pdf", "pointer": "Page 1", "notes": ""}
    ],
    "representment_rationale": "Rationale text.",
    "recommended_action": "represent",
    "justification": "Merchant has compelling evidence.",
    "confidence": "High",
    "request_more_evidence": [],
    "uncertainties": [],
    "analyst_review_notes": [],
}


def test_valid_workup_passes():
    ok, errors = validate_workup(_VALID)
    assert ok
    assert errors == []


def test_missing_required_key_fails():
    bad = {k: v for k, v in _VALID.items() if k != "recommended_action"}
    ok, errors = validate_workup(bad)
    assert not ok
    assert any("recommended_action" in e for e in errors)


def test_invalid_action_fails():
    ok, errors = validate_workup({**_VALID, "recommended_action": "do_nothing"})
    assert not ok


def test_invalid_confidence_fails():
    ok, errors = validate_workup({**_VALID, "confidence": "Very High"})
    assert not ok


def test_valid_actions_are_complete():
    assert VALID_ACTIONS == {"represent", "accept_liability", "request_more_evidence"}
