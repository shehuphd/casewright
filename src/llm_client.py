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
    import openai
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

    try:
        response = client.chat.completions.create(**params)
    except openai.AuthenticationError:
        raise ValueError("Invalid API key. Update it in Settings.")
    except openai.RateLimitError as e:
        msg = str(e).lower()
        if any(w in msg for w in ("quota", "exceeded", "billing", "insufficient")):
            raise ValueError("Your OpenAI account has no remaining credits. Add billing at platform.openai.com.")
        raise ValueError("OpenAI rate limit reached. Wait a moment and try again.")
    except openai.NotFoundError:
        raise ValueError(f"Model '{model}' not found. Choose a different model in Settings.")
    except openai.BadRequestError as e:
        raise ValueError(f"OpenAI rejected the request: {e}")
    except openai.APIConnectionError:
        raise ValueError("Could not reach OpenAI. Check your internet connection.")
    except openai.APITimeoutError:
        raise ValueError("The request timed out. Try again, or try a smaller case.")
    except openai.InternalServerError:
        raise ValueError("OpenAI is experiencing issues. Try again shortly.")

    try:
        raw = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else _estimate_tokens(system_prompt, text_prompt)
        return json.loads(raw), tokens
    except json.JSONDecodeError:
        raise ValueError("The model returned an unexpected response format. Try again.")


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

def _anthropic_supports_temperature(model: str) -> bool:
    """Opus 4.7+, Opus 4.8, Sonnet 5, and Fable 5 dropped temperature — it returns 400."""
    no_temp = {"claude-opus-4-7", "claude-opus-4-8", "claude-sonnet-5", "claude-fable-5", "claude-mythos-5"}
    return model not in no_temp


def _call_anthropic(system_prompt, text_prompt, image_parts, api_key, model):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    user_content = _anthropic_content(text_prompt, image_parts)

    params: dict = {
        "model": model,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
        "max_tokens": 8192,
    }
    if _anthropic_supports_temperature(model):
        params["temperature"] = 0.1

    try:
        response = client.messages.create(**params)
    except anthropic.AuthenticationError:
        raise ValueError("Invalid API key. Update it in Settings.")
    except anthropic.RateLimitError as e:
        msg = str(e).lower()
        if any(w in msg for w in ("quota", "exceeded", "billing", "credit", "insufficient")):
            raise ValueError("Your Anthropic account has no remaining credits. Add billing at console.anthropic.com.")
        raise ValueError("Anthropic rate limit reached. Wait a moment and try again.")
    except anthropic.NotFoundError:
        raise ValueError(f"Model '{model}' not found. Choose a different model in Settings.")
    except anthropic.BadRequestError as e:
        raise ValueError(f"Anthropic rejected the request: {e}")
    except anthropic.APIConnectionError:
        raise ValueError("Could not reach Anthropic. Check your internet connection.")
    except anthropic.APITimeoutError:
        raise ValueError("The request timed out. Try again, or try a smaller case.")
    except anthropic.InternalServerError:
        raise ValueError("Anthropic is experiencing issues. Try again shortly.")

    try:
        raw = response.content[0].text if response.content else ""
        tokens = (
            response.usage.input_tokens + response.usage.output_tokens
            if response.usage else _estimate_tokens(system_prompt, text_prompt)
        )
        return _extract_json(raw), tokens
    except json.JSONDecodeError:
        raise ValueError("The model returned an unexpected response format. Try again.")


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
