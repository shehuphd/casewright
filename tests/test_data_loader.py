from src.data_loader import load_cases, get_case

_REQUIRED_FIELDS = {"case_id", "scheme", "reason_code", "reason_code_label",
                    "chargeback_amount", "chargeback_date", "transaction",
                    "merchant_evidence_documents"}


def test_load_cases_count():
    cases, errors = load_cases()
    assert len(cases) == 10


def test_load_cases_no_errors():
    _, errors = load_cases()
    assert errors == []


def test_all_cases_have_required_fields():
    cases, _ = load_cases()
    for c in cases:
        missing = _REQUIRED_FIELDS - set(c.keys())
        assert not missing, f"{c.get('case_id')} missing: {missing}"


def test_get_case_returns_correct():
    c = get_case("CB-2025-0001")
    assert c is not None
    assert c["case_id"] == "CB-2025-0001"


def test_get_case_missing_returns_none():
    assert get_case("FAKE-9999") is None


def test_schemes_are_visa_or_mastercard():
    cases, _ = load_cases()
    for c in cases:
        assert c["scheme"] in {"visa", "mastercard"}, f"Unexpected scheme in {c['case_id']}"
