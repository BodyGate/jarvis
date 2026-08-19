"""Test per la classificazione di intenti (RF-003)."""
import json
from unittest.mock import Mock, patch

import pytest
import requests

from app.config import Settings
from app.router import RouterError, classify_image_message, classify_intent


def _settings(groq_api_key="test-key"):
    return Settings(
        flask_env="development",
        secret_key="s",
        app_password_hash=None,
        supabase_url=None,
        supabase_key=None,
        database_url=None,
        groq_api_key=groq_api_key,
        gemini_api_key=None,
        openweather_api_key=None,
        google_client_id=None,
        google_client_secret=None,
        google_redirect_uri=None,
        token_encryption_key=None,
        external_service_timeout_seconds=5,
    )


def _groq_response(content: dict) -> Mock:
    mock = Mock()
    mock.raise_for_status = Mock()
    mock.json.return_value = {"choices": [{"message": {"content": json.dumps(content)}}]}
    return mock


def test_classify_intent_returns_parsed_classification():
    settings = _settings()
    with patch("app.router.requests.post") as mock_post:
        mock_post.return_value = _groq_response(
            {"intent": "coding", "target": "claude", "confidence": 0.9}
        )
        result = classify_intent("scrivi uno script", settings)

    assert result == {"intent": "coding", "target": "claude", "confidence": 0.9}


def test_classify_intent_falls_back_to_local_on_invalid_target():
    settings = _settings()
    with patch("app.router.requests.post") as mock_post:
        mock_post.return_value = _groq_response(
            {"intent": "vision", "target": "gemini", "confidence": 0.8}
        )
        result = classify_intent("descrivi questa foto", settings)

    assert result["target"] == "local"


def test_classify_intent_raises_without_api_key():
    settings = _settings(groq_api_key=None)
    with pytest.raises(RouterError):
        classify_intent("qualsiasi cosa", settings)


def test_classify_intent_raises_on_network_error():
    settings = _settings()
    with patch("app.router.requests.post", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(RouterError):
            classify_intent("qualsiasi cosa", settings)


def test_classify_intent_raises_on_malformed_json():
    settings = _settings()
    with patch("app.router.requests.post") as mock_post:
        mock = Mock()
        mock.raise_for_status = Mock()
        mock.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
        mock_post.return_value = mock
        with pytest.raises(RouterError):
            classify_intent("qualsiasi cosa", settings)


def test_classify_image_message_always_targets_gemini():
    assert classify_image_message() == {"intent": "vision", "target": "gemini", "confidence": 1.0}
