import os
from pathlib import Path
from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


def get_settings():
    load_dotenv(ENV_FILE, override=True)
    provider = os.getenv("LLM_PROVIDER", "")
    api_key = os.getenv("LLM_API_KEY", "")
    text_model = os.getenv("LLM_TEXT_MODEL", "gpt-4.1-mini")
    vision_model = os.getenv("LLM_VISION_MODEL", "gpt-4.1-mini")
    documents_dir = os.getenv("DOCUMENTS_DIR", "") or str(BASE_DIR / "data" / "documents")

    key_preview = None
    if api_key and len(api_key) > 8:
        key_preview = api_key[:6] + "••••••••" + api_key[-4:]
    elif api_key:
        key_preview = "••••••••"

    return {
        "provider": provider or None,
        "api_key_set": bool(api_key),
        "api_key_preview": key_preview,
        "text_model": text_model,
        "vision_model": vision_model,
        "documents_dir": documents_dir,
    }


def get_raw_settings():
    load_dotenv(ENV_FILE, override=True)
    return {
        "provider": os.getenv("LLM_PROVIDER", ""),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "text_model": os.getenv("LLM_TEXT_MODEL", "gpt-4.1-mini"),
        "vision_model": os.getenv("LLM_VISION_MODEL", "gpt-4.1-mini"),
        "documents_dir": os.getenv("DOCUMENTS_DIR", "") or str(BASE_DIR / "data" / "documents"),
    }


def save_settings(provider: str, api_key: str, text_model: str, vision_model: str):
    ENV_FILE.touch(exist_ok=True)
    if provider:
        set_key(str(ENV_FILE), "LLM_PROVIDER", provider)
    if api_key:
        set_key(str(ENV_FILE), "LLM_API_KEY", api_key)
    if text_model:
        set_key(str(ENV_FILE), "LLM_TEXT_MODEL", text_model)
    if vision_model:
        set_key(str(ENV_FILE), "LLM_VISION_MODEL", vision_model)
    load_dotenv(ENV_FILE, override=True)


def delete_api_key():
    ENV_FILE.touch(exist_ok=True)
    set_key(str(ENV_FILE), "LLM_API_KEY", "")
    set_key(str(ENV_FILE), "LLM_TEXT_MODEL", "")
    set_key(str(ENV_FILE), "LLM_VISION_MODEL", "")
    load_dotenv(ENV_FILE, override=True)
