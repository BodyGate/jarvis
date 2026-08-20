"""Test per la persistenza cifrata dei token Google (app.google_tokens_repo)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.config import Settings
from app.google_oauth import GoogleOAuthError
from app.google_tokens_repo import (
    delete_tokens,
    ensure_valid_access_token,
    get_tokens,
    is_expired,
    save_tokens,
)
from app.token_crypto import encrypt_token
from tests.fake_supabase import FakeSupabaseClient

VALID_KEY = "0" * 64


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
        google_client_id=None,
        google_client_secret=None,
        google_redirect_uri=None,
        token_encryption_key=VALID_KEY,
        external_service_timeout_seconds=5,
    )
    base.update(overrides)
    return Settings(**base)


def test_save_and_get_tokens_roundtrip():
    db = FakeSupabaseClient()
    settings = _settings()

    save_tokens(
        db,
        settings,
        {"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600, "scope": "a b c"},
    )
    tokens = get_tokens(db, settings)

    assert tokens["access_token"] == "at1"
    assert tokens["refresh_token"] == "rt1"
    assert tokens["scopes"] == ["a", "b", "c"]


def test_save_first_time_without_refresh_token_raises():
    db = FakeSupabaseClient()
    settings = _settings()

    with pytest.raises(ValueError):
        save_tokens(db, settings, {"access_token": "at1", "expires_in": 3600})


def test_save_update_keeps_existing_refresh_token_and_scopes():
    db = FakeSupabaseClient()
    settings = _settings()

    save_tokens(
        db, settings, {"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600, "scope": "a b"}
    )
    # Un refresh tipico non restituisce refresh_token né scope
    save_tokens(db, settings, {"access_token": "at2", "expires_in": 3600})

    tokens = get_tokens(db, settings)
    assert tokens["access_token"] == "at2"
    assert tokens["refresh_token"] == "rt1"
    assert tokens["scopes"] == ["a", "b"]


def test_get_tokens_returns_none_when_not_connected():
    db = FakeSupabaseClient()
    settings = _settings()
    assert get_tokens(db, settings) is None


def test_delete_tokens_removes_row():
    db = FakeSupabaseClient()
    settings = _settings()
    save_tokens(db, settings, {"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600})

    delete_tokens(db)

    assert get_tokens(db, settings) is None


def test_is_expired_true_when_missing():
    assert is_expired(None) is True


def test_is_expired_false_for_future_timestamp():
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert is_expired(future) is False


def test_is_expired_true_for_past_timestamp():
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert is_expired(past) is True


def test_ensure_valid_access_token_raises_when_not_connected():
    db = FakeSupabaseClient()
    settings = _settings()
    with pytest.raises(GoogleOAuthError):
        ensure_valid_access_token(db, settings)


def test_ensure_valid_access_token_returns_existing_when_not_expired():
    db = FakeSupabaseClient()
    settings = _settings()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    db.table("google_tokens").insert(
        {
            "user_id": "default",
            "provider": "google",
            "access_token": encrypt_token("at-valid", settings),
            "refresh_token": encrypt_token("rt", settings),
            "expires_at": future,
        }
    ).execute()

    token = ensure_valid_access_token(db, settings)
    assert token == "at-valid"


def test_ensure_valid_access_token_refreshes_when_expired():
    db = FakeSupabaseClient()
    settings = _settings()
    save_tokens(
        db, settings, {"access_token": "old-at", "refresh_token": "rt", "expires_in": -10}
    )

    with patch(
        "app.google_tokens_repo.refresh_access_token", return_value={"access_token": "new-at"}
    ):
        token = ensure_valid_access_token(db, settings)

    assert token == "new-at"
    assert get_tokens(db, settings)["refresh_token"] == "rt"  # invariato
