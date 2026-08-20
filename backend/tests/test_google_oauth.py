"""Test per il client OAuth Google (app.google_oauth)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.config import Settings
from app.google_oauth import (
    GoogleOAuthError,
    build_authorization_url,
    exchange_code,
    refresh_access_token,
    revoke_token,
)


def _settings(**overrides):
    base = dict(
        flask_env="development",
        secret_key="s",
        app_password_hash=None,
        supabase_url=None,
        supabase_key=None,
        database_url=None,
        groq_api_key=None,
        gemini_api_key=None,
        openweather_api_key=None,
        google_client_id="client-id",
        google_client_secret="client-secret",
        google_redirect_uri="https://example.com/auth/callback",
        token_encryption_key=None,
        external_service_timeout_seconds=5,
    )
    base.update(overrides)
    return Settings(**base)


def test_build_authorization_url_raises_without_config():
    settings = _settings(google_client_id=None)
    with pytest.raises(GoogleOAuthError):
        build_authorization_url(settings)


def test_build_authorization_url_returns_uri_and_state():
    settings = _settings()
    fake_client = MagicMock()
    fake_client.create_authorization_url.return_value = ("https://accounts.google.com/...", "abc123")
    with patch("app.google_oauth._client", return_value=fake_client):
        uri, state = build_authorization_url(settings)

    assert uri == "https://accounts.google.com/..."
    assert state == "abc123"
    fake_client.create_authorization_url.assert_called_once()
    _, kwargs = fake_client.create_authorization_url.call_args
    assert kwargs["access_type"] == "offline"
    assert kwargs["prompt"] == "consent"


def test_exchange_code_returns_token_dict():
    settings = _settings()
    fake_client = MagicMock()
    fake_client.fetch_token.return_value = {"access_token": "at", "refresh_token": "rt"}
    with patch("app.google_oauth._client", return_value=fake_client):
        token = exchange_code("auth-code", settings)

    assert token == {"access_token": "at", "refresh_token": "rt"}


def test_exchange_code_wraps_network_errors():
    settings = _settings()
    fake_client = MagicMock()
    fake_client.fetch_token.side_effect = requests.ConnectionError("boom")
    with patch("app.google_oauth._client", return_value=fake_client):
        with pytest.raises(GoogleOAuthError):
            exchange_code("auth-code", settings)


def test_refresh_access_token_returns_new_token():
    settings = _settings()
    fake_client = MagicMock()
    fake_client.refresh_token.return_value = {"access_token": "new-at"}
    with patch("app.google_oauth._client", return_value=fake_client):
        token = refresh_access_token("old-rt", settings)

    assert token == {"access_token": "new-at"}


def test_revoke_token_succeeds_on_200():
    settings = _settings()
    fake_response = MagicMock(status_code=200)
    with patch("app.google_oauth.requests.post", return_value=fake_response):
        revoke_token("some-token", settings)  # non deve sollevare


def test_revoke_token_raises_on_unexpected_status():
    settings = _settings()
    fake_response = MagicMock(status_code=500)
    with patch("app.google_oauth.requests.post", return_value=fake_response):
        with pytest.raises(GoogleOAuthError):
            revoke_token("some-token", settings)
