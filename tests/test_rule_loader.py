from src.rule_loader import get_rule, format_rule_text


def test_get_valid_visa_rule():
    rule = get_rule("visa", "10.4")
    assert rule is not None
    assert rule["scheme"] == "visa"
    assert rule["code"] == "10.4"
    assert "requirements" in rule


def test_get_valid_mastercard_rule():
    rule = get_rule("mastercard", "4837")
    assert rule is not None
    assert rule["scheme"] == "mastercard"
    assert rule["code"] == "4837"


def test_unknown_code_returns_none():
    assert get_rule("visa", "99.99") is None


def test_unknown_scheme_returns_none():
    assert get_rule("amex", "4837") is None


def test_format_rule_text_is_readable():
    rule = get_rule("visa", "10.4")
    text = format_rule_text(rule)
    assert isinstance(text, str)
    assert len(text) > 20


def test_non_representable_flagged():
    rule = get_rule("visa", "10.5")
    assert rule is not None
    assert rule.get("non_representable") is True


def test_all_rules_have_required_fields():
    for code in ["10.4", "10.5", "10.1", "10.2"]:
        rule = get_rule("visa", code)
        if rule:
            assert "label" in rule
            assert "requirements" in rule
