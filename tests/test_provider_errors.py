"""Adversarial tests for the provider-error translation layer.

The failure mode this guards against: an isinstance() branch matching the
wrong exception class (or never matching at all) silently falls through to
the generic "could not verify" message, hiding what actually went wrong
without raising anything — no exception, no test failure, just a worse
message. Each case here constructs a *real* SDK exception (not a mock) and
asserts the specific branch fired, not just that some string came back.
"""
import httpx
import openai
import anthropic
import pytest

from app import _friendly_provider_error


def _status_error(cls, status_code=400):
    """Build a real APIStatusError subclass instance the way the SDK does:
    it needs an httpx.Response, not just a message string."""
    request = httpx.Request("GET", "https://example.invalid/v1/models")
    response = httpx.Response(status_code, request=request, json={"error": {"message": "boom"}})
    return cls("boom", response=response, body=None)


def _connection_error(cls):
    request = httpx.Request("GET", "https://example.invalid/v1/models")
    return cls(request=request)


GENERIC = "Could not verify this key. Try again, or check the provider's status page."


@pytest.mark.parametrize("cls", [openai.AuthenticationError, anthropic.AuthenticationError])
def test_authentication_error_is_translated(cls):
    msg = _friendly_provider_error(_status_error(cls, 401))
    assert "rejected" in msg
    assert msg != GENERIC


@pytest.mark.parametrize("cls", [openai.PermissionDeniedError, anthropic.PermissionDeniedError])
def test_permission_denied_is_translated(cls):
    msg = _friendly_provider_error(_status_error(cls, 403))
    assert "permission" in msg
    assert msg != GENERIC


@pytest.mark.parametrize("cls", [openai.RateLimitError, anthropic.RateLimitError])
def test_rate_limit_is_translated(cls):
    msg = _friendly_provider_error(_status_error(cls, 429))
    assert "rate-limiting" in msg
    assert msg != GENERIC


def test_anthropic_overloaded_is_translated():
    msg = _friendly_provider_error(_status_error(anthropic.OverloadedError, 529))
    assert "overloaded" in msg
    assert msg != GENERIC


@pytest.mark.parametrize("cls", [openai.APIConnectionError, anthropic.APIConnectionError])
def test_connection_error_is_translated(cls):
    msg = _friendly_provider_error(_connection_error(cls))
    assert "connection" in msg.lower()
    assert msg != GENERIC


@pytest.mark.parametrize("cls", [openai.InternalServerError, anthropic.InternalServerError])
def test_internal_server_error_is_translated(cls):
    msg = _friendly_provider_error(_status_error(cls, 500))
    assert "issues" in msg
    assert msg != GENERIC


def test_unrecognised_exception_gets_the_generic_fallback_not_a_crash():
    """A wholly unexpected exception type must degrade gracefully, not raise
    out of the error handler itself."""
    assert _friendly_provider_error(RuntimeError("something unrelated")) == GENERIC


def test_friendly_message_never_contains_the_raw_key_material():
    """The whole point: the provider's own redacted-key rendering (a long run
    of asterisks) and the raw dict-repr body must never reach the analyst."""
    request = httpx.Request("GET", "https://example.invalid/v1/models")
    response = httpx.Response(
        401, request=request,
        json={"error": {"message": "Incorrect API key provided: sk-proj-" + "*" * 60 + "pQKQ",
                        "type": "invalid_request_error", "code": "invalid_api_key"}},
    )
    e = openai.AuthenticationError(
        "Incorrect API key provided: sk-proj-" + "*" * 60 + "pQKQ", response=response, body=None
    )
    msg = _friendly_provider_error(e)
    assert "*" not in msg
    assert "sk-proj" not in msg
    assert "invalid_request_error" not in msg
