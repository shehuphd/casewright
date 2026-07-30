"""Adversarial tests for bring-your-own-key credential resolution.

The property under test is negative: in cloud mode the server must never
supply a key of its own. An unauthenticated instance that falls back to an
operator key lets anyone with the URL spend the operator's credit, which is
the failure this whole path exists to prevent.
"""
import pytest

import src.config as cfg


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(cfg, "get_deployment_mode", lambda: "cloud")


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(cfg, "get_deployment_mode", lambda: "local")


@pytest.fixture
def client():
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


# ── The server must not leak its own key in cloud mode ────────────────────────

def test_cloud_never_falls_back_to_the_server_key(cloud, monkeypatch):
    """The landmine: an operator .env present on the host must stay unused."""
    monkeypatch.setattr(cfg, "get_raw_settings", lambda: {
        "provider": "openai", "api_key": "sk-OPERATOR-SECRET",
        "text_model": "gpt-4.1", "vision_model": "gpt-4.1", "documents_dir": "/x",
    })
    assert cfg.resolve_settings()["api_key"] == ""
    assert cfg.resolve_settings({})["api_key"] == ""
    assert cfg.resolve_settings({"api_key": ""})["api_key"] == ""
    assert cfg.resolve_settings({"api_key": None})["api_key"] == ""


def test_cloud_uses_the_callers_key_not_the_servers(cloud, monkeypatch):
    monkeypatch.setattr(cfg, "get_raw_settings", lambda: {
        "provider": "anthropic", "api_key": "sk-OPERATOR-SECRET",
        "text_model": "claude", "vision_model": "claude", "documents_dir": "/x",
    })
    got = cfg.resolve_settings({"provider": "openai", "api_key": "sk-caller"})
    assert got["api_key"] == "sk-caller"
    assert got["provider"] == "openai"


def test_onboarding_does_not_report_a_server_key_in_cloud(client, monkeypatch):
    """The badge bug: a developer's local .env reported 'key detected' on the
    cloud card, describing their own machine rather than the deployment."""
    monkeypatch.setattr(cfg, "get_deployment_mode", lambda: "cloud")
    monkeypatch.setattr(cfg, "get_raw_settings", lambda: {
        "provider": "openai", "api_key": "sk-LOCAL-DEV-KEY",
        "text_model": "gpt-4.1", "vision_model": "gpt-4.1", "documents_dir": "/x",
    })
    body = client.get("/api/onboarding").get_json()
    assert body["key_configured"] is False
    assert body["provider"] is None
    assert "sk-LOCAL-DEV-KEY" not in client.get("/api/onboarding").get_data(as_text=True)


def test_onboarding_still_reports_the_key_locally(client, monkeypatch):
    monkeypatch.setattr(cfg, "get_deployment_mode", lambda: "local")
    monkeypatch.setattr(cfg, "get_raw_settings", lambda: {
        "provider": "openai", "api_key": "sk-local",
        "text_model": "gpt-4.1", "vision_model": "gpt-4.1", "documents_dir": "/x",
    })
    body = client.get("/api/onboarding").get_json()
    assert body["key_configured"] is True
    assert body["provider"] == "openai"


# ── A caller must not reach the filesystem through settings ───────────────────

def test_documents_dir_cannot_be_supplied_by_the_caller(cloud):
    """documents_dir feeds a file read. Honouring a caller-supplied value
    would turn a settings field into arbitrary filesystem access."""
    for hostile in ("/etc", "../../../../etc", "/", None, ""):
        got = cfg.resolve_settings({"api_key": "sk-x", "documents_dir": hostile})
        assert got["documents_dir"].endswith("data/documents"), hostile


# ── Malformed caller input degrades rather than crashing ──────────────────────

def test_provider_is_normalised(cloud):
    for raw, want in [("  OpenAI  ", "openai"), ("ANTHROPIC", "anthropic"),
                      (None, ""), ("", "")]:
        assert cfg.resolve_settings({"provider": raw, "api_key": "k"})["provider"] == want


def test_missing_models_fall_back_to_a_default(cloud):
    got = cfg.resolve_settings({"api_key": "k"})
    assert got["text_model"] == "gpt-4.1-mini"
    assert got["vision_model"] == "gpt-4.1-mini"


def test_vision_model_defaults_to_the_text_model(cloud):
    """A caller who picks a text model but no vision model should not silently
    get a different model for images than the one they chose."""
    got = cfg.resolve_settings({"api_key": "k", "text_model": "gpt-5"})
    assert got["vision_model"] == "gpt-5"


def test_resolve_settings_returns_every_key_call_llm_reads(cloud, local):
    """call_llm indexes these directly; a missing key is an AttributeError at
    analysis time rather than a clear configuration error."""
    for supplied in ({}, {"api_key": "k"}, {"provider": "openai", "api_key": "k"}):
        got = cfg.resolve_settings(supplied)
        assert set(got) >= {"provider", "api_key", "text_model", "vision_model", "documents_dir"}


# ── Local mode is unchanged ───────────────────────────────────────────────────

def test_local_ignores_caller_supplied_credentials(local, monkeypatch):
    """Locally the operator and the analyst are the same person, and .env is
    authoritative. A stray header must not override it."""
    monkeypatch.setattr(cfg, "get_raw_settings", lambda: {
        "provider": "openai", "api_key": "sk-from-env",
        "text_model": "gpt-4.1", "vision_model": "gpt-4.1", "documents_dir": "/x",
    })
    got = cfg.resolve_settings({"api_key": "sk-injected", "provider": "anthropic"})
    assert got["api_key"] == "sk-from-env"
    assert got["provider"] == "openai"
