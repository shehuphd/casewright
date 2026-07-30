import os
import re
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


def _set_key(env_path: Path, key: str, value: str) -> None:
    """Write a key=value pair to .env directly (avoids dotenv's temp-file rename which fails on Windows/Dropbox)."""
    env_path.touch(exist_ok=True)
    content = env_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    quoted = f'"{value}"'
    replacement = f"{key}={quoted}"
    if pattern.search(content):
        content = pattern.sub(replacement, content)
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        content += replacement + "\n"
    env_path.write_text(content, encoding="utf-8")


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
    if provider:
        _set_key(ENV_FILE, "LLM_PROVIDER", provider)
    if api_key:
        _set_key(ENV_FILE, "LLM_API_KEY", api_key)
    if text_model:
        _set_key(ENV_FILE, "LLM_TEXT_MODEL", text_model)
    if vision_model:
        _set_key(ENV_FILE, "LLM_VISION_MODEL", vision_model)
    load_dotenv(ENV_FILE, override=True)


def delete_api_key():
    _set_key(ENV_FILE, "LLM_API_KEY", "")
    _set_key(ENV_FILE, "LLM_TEXT_MODEL", "")
    _set_key(ENV_FILE, "LLM_VISION_MODEL", "")
    load_dotenv(ENV_FILE, override=True)


def resolve_settings(supplied: dict | None = None) -> dict:
    """Credentials for a single request.

    Cloud deployments are bring-your-own-key: the analyst's key arrives with
    the request, is used for that call, and is never written down. The server
    holds no key of its own, so an unauthenticated instance can't spend the
    operator's credit, and one analyst's key can't serve another's request.

    Local runs read .env as before, where the operator and the analyst are the
    same person.

    documents_dir is always server-side. Letting a caller supply it would turn
    a settings field into arbitrary filesystem read.
    """
    if get_deployment_mode() != "cloud":
        return get_raw_settings()

    supplied = supplied or {}
    text_model = supplied.get("text_model") or "gpt-4.1-mini"
    return {
        "provider": (supplied.get("provider") or "").lower().strip(),
        "api_key": supplied.get("api_key") or "",
        "text_model": text_model,
        "vision_model": supplied.get("vision_model") or text_model,
        "documents_dir": os.getenv("DOCUMENTS_DIR", "") or str(BASE_DIR / "data" / "documents"),
    }


def get_deployment_mode() -> str:
    """Return 'cloud' or 'local'. Operators set DEPLOYMENT_MODE=cloud in ACA env vars."""
    return os.getenv("DEPLOYMENT_MODE", "local").lower()


def env_file_exists() -> bool:
    return ENV_FILE.exists()
