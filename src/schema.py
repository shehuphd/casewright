VALID_ACTIONS = {"represent", "accept_liability", "request_more_evidence"}
VALID_STATUSES = {"satisfied", "partial", "missing", "needs_review", "not_applicable", "invalid"}
VALID_CONFIDENCE = {"High", "Medium", "Low"}

REQUIRED_WORKUP_FIELDS = [
    "case_id",
    "reason_code_summary",
    "evidence_assessment",
    "representment_rationale",
    "recommended_action",
    "justification",
    "confidence",
    "request_more_evidence",
    "uncertainties",
    "analyst_review_notes",
]

OUTPUT_SCHEMA = """{
  "case_id": "string",
  "reason_code_summary": {
    "issuer_allegation": "plain-English restatement of what the issuer is claiming",
    "scheme_requirement_summary": "plain-English summary of what the scheme requires to defend this reason code"
  },
  "evidence_assessment": [
    {
      "requirement": "the requirement text from the reason-code rules",
      "status": "satisfied | partial | missing | needs_review | not_applicable | invalid",
      "supporting_document": "filename.pdf or null if no document addresses this",
      "pointer": "Page X / section reference or null",
      "notes": "specific, traceable explanation of why this status was assigned"
    }
  ],
  "representment_rationale": "3-5 sentence rationale the analyst can edit and file",
  "recommended_action": "represent | accept_liability | request_more_evidence",
  "justification": "one sentence explaining the recommended action",
  "confidence": "High | Medium | Low",
  "request_more_evidence": ["specific item to request from the merchant if action is request_more_evidence"],
  "uncertainties": ["any uncertainty in the evidence assessment the analyst should know about"],
  "analyst_review_notes": ["specific things the analyst should double-check before filing"]
}"""


def validate_workup(data: dict) -> tuple[bool, list[str]]:
    errors = []
    for field in REQUIRED_WORKUP_FIELDS:
        if field not in data:
            errors.append(f"Missing field: {field}")
    if "recommended_action" in data and data["recommended_action"] not in VALID_ACTIONS:
        errors.append(f"Invalid recommended_action: {data['recommended_action']!r}")
    if "confidence" in data and data["confidence"] not in VALID_CONFIDENCE:
        errors.append(f"Invalid confidence: {data['confidence']!r}")
    if "evidence_assessment" in data:
        for i, item in enumerate(data["evidence_assessment"]):
            if "status" in item and item["status"] not in VALID_STATUSES:
                errors.append(f"evidence_assessment[{i}] invalid status: {item['status']!r}")
    return len(errors) == 0, errors
