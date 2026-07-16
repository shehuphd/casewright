import pytest

_ENV_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_TEXT_MODEL", "LLM_VISION_MODEL")


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Patch ENV_FILE to a temp path and wipe config keys before each test.
    monkeypatch auto-restores both the attribute and the original env values on teardown."""
    import src.config as cfg
    monkeypatch.setattr(cfg, "ENV_FILE", tmp_path / ".env")
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield tmp_path / ".env"


def test_save_and_read_settings(isolated_env):
    import src.config as cfg
    cfg.save_settings(
        provider="openai",
        api_key="sk-testkey12345",
        text_model="gpt-4.1-mini",
        vision_model="gpt-4.1-mini",
    )
    assert isolated_env.exists()
    settings = cfg.get_settings()
    assert settings["provider"] == "openai"
    assert settings["api_key_set"] is True
    assert settings["text_model"] == "gpt-4.1-mini"


def test_key_preview_obfuscation(isolated_env):
    import src.config as cfg
    cfg.save_settings(
        provider="anthropic",
        api_key="sk-ant-testabc1234xyz9",
        text_model="claude-haiku-4-5",
        vision_model="claude-haiku-4-5",
    )
    settings = cfg.get_settings()
    preview = settings["api_key_preview"]
    assert "••••••••" in preview
    assert preview.startswith("sk-ant")
    assert "xyz9" in preview
    assert "testabc1234" not in preview


def test_empty_key_returns_not_set(isolated_env):
    import src.config as cfg
    settings = cfg.get_settings()
    assert settings["api_key_set"] is False
    assert settings["api_key_preview"] is None
