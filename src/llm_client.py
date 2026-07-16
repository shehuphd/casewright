import json
import re


def call_llm(
    system_prompt: str,
    text_prompt: str,
    image_parts: list[dict],
    settings: dict,
) -> tuple[dict, int]:
    """Call the configured LLM. Returns (parsed_workup, token_count)."""
    provider = (settings.get("provider") or "").lower()
    api_key = settings.get("api_key", "")
    text_model = settings.get("text_model") or "gpt-4.1-mini"

    if not provider or not api_key:
        raise ValueError("No LLM provider or API key configured. Open Settings to add one.")

    if provider == "openai":
        return _call_openai(system_prompt, text_prompt, image_parts, api_key, text_model)
    if provider == "anthropic":
        return _call_anthropic(system_prompt, text_prompt, image_parts, api_key, text_model)
    raise ValueError(f"Unknown provider: {provider!r}. Supported: openai, anthropic.")


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _supports_temperature(model: str) -> bool:
    """GPT-5 and o-series models only accept temperature=1 (the default); omit it for those."""
    return not (model.startswith("gpt-5") or re.match(r"^o\d", model))


def _call_openai(system_prompt, text_prompt, image_parts, api_key, model):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    user_content = _openai_content(text_prompt, image_parts)

    params: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 8192,
    }
    if _supports_temperature(model):
        params["temperature"] = 0.1

    response = client.chat.completions.create(**params)

    raw = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else _estimate_tokens(system_prompt, text_prompt)
    return json.loads(raw), tokens


def _openai_content(text_prompt: str, image_parts: list[dict]) -> list | str:
    if not image_parts:
        return text_prompt
    parts = []
    for img in image_parts:
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img['mime']};base64,{img['data']}"},
        })
        parts.append({"type": "text", "text": f"[Image above is: {img['filename']}]"})
    parts.append({"type": "text", "text": text_prompt})
    return parts


# ── Anthropic ─────────────────────────────────────────────────────────────────

def _call_anthropic(system_prompt, text_prompt, image_parts, api_key, model):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    user_content = _anthropic_content(text_prompt, image_parts)

    response = client.messages.create(
        model=model,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        max_tokens=8192,
    )

    raw = response.content[0].text if response.content else ""
    tokens = (
        response.usage.input_tokens + response.usage.output_tokens
        if response.usage else _estimate_tokens(system_prompt, text_prompt)
    )
    return _extract_json(raw), tokens


def _anthropic_content(text_prompt: str, image_parts: list[dict]) -> list | str:
    if not image_parts:
        return text_prompt
    parts = []
    for img in image_parts:
        parts.append({
            "type": "image",
            "source": {"type": "base64", "media_type": img["mime"], "data": img["data"]},
        })
        parts.append({"type": "text", "text": f"[Image above is: {img['filename']}]"})
    parts.append({"type": "text", "text": text_prompt})
    return parts


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Extract JSON object from text that may contain surrounding prose."""
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")


def _estimate_tokens(system_prompt: str, text_prompt: str) -> int:
    return (len(system_prompt) + len(text_prompt)) // 4
