from src.data_loader import get_case
from src.prompt_builder import build_prompt
from src.rule_loader import get_rule


def _case_and_rule(case_id="CB-2025-0001"):
    case = get_case(case_id)
    rule = get_rule(case["scheme"], case["reason_code"])
    return case, rule


def test_build_prompt_returns_strings():
    case, rule = _case_and_rule()
    system_prompt, text_prompt, image_parts = build_prompt(case, rule, [])
    assert isinstance(system_prompt, str) and len(system_prompt) > 50
    assert isinstance(text_prompt, str) and len(text_prompt) > 50
    assert isinstance(image_parts, list)


def test_no_image_parts_for_pdf_docs():
    case, rule = _case_and_rule()
    docs = [{"filename": "invoice.pdf", "file_type": "pdf", "full_text": "Invoice text.", "status": "success"}]
    _, _, image_parts = build_prompt(case, rule, docs)
    assert image_parts == []


def test_image_part_included_for_image_doc():
    case, rule = _case_and_rule()
    docs = [{"filename": "receipt.jpg", "file_type": "image", "image_data": "base64abc==", "image_mime": "image/jpeg", "status": "image"}]
    _, _, image_parts = build_prompt(case, rule, docs)
    assert len(image_parts) == 1


def test_prompt_contains_case_id():
    case, rule = _case_and_rule()
    _, text_prompt, _ = build_prompt(case, rule, [])
    assert "CB-2025-0001" in text_prompt


def test_prompt_contains_reason_code():
    case, rule = _case_and_rule()
    _, text_prompt, _ = build_prompt(case, rule, [])
    assert case["reason_code"] in text_prompt
