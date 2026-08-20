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
            {"intent": "coding", "target": "claude", "specialist": "other", "confidence": 0.9}
        )
        result = classify_intent("scrivi uno script", settings)

    assert result == {
        "intent": "coding",
        "target": "claude",
        "specialist": None,
        "city": None,
        "date_range": None,
        "event_title": None,
        "event_date": None,
        "event_time": None,
        "confidence": 0.9,
    }


def test_classify_intent_returns_specialist_for_local_target():
    settings = _settings()
    with patch("app.router.requests.post") as mock_post:
        mock_post.return_value = _groq_response(
            {"intent": "weather_query", "target": "local", "specialist": "weather", "city": "Roma", "confidence": 0.9}
        )
        result = classify_intent("che tempo fa a Roma", settings)

    assert result["target"] == "local"
    assert result["specialist"] == "weather"
    assert result["city"] == "Roma"


def test_classify_intent_ignores_city_for_non_weather_specialist():
    settings = _settings()
    with patch("app.router.requests.post") as mock_post:
        mock_post.return_value = _groq_response(
            {"intent": "web_search", "target": "local", "specialist": "search", "city": "Roma", "confidence": 0.9}
        )
        result = classify_intent("cerca qualcosa su Roma", settings)

    assert result["city"] is None


def test_classify_intent_falls_back_to_other_specialist_when_unexpected():
    settings = _settings()
    with patch("app.router.requests.post") as mock_post:
        mock_post.return_value = _groq_response(
            {"intent": "boh", "target": "local", "specialist": "not-a-real-specialist", "confidence": 0.5}
        )
        result = classify_intent("qualcosa di strano", settings)

    assert result["specialist"] == "other"


def test_classify_intent_falls_back_to_local_on_invalid_target():
    settings = _settings()
    with patch("app.router.requests.post") as mock_post:
        mock_post.return_value = _groq_response(
            {"intent": "vision", "target": "gemini", "specialist": "other", "confidence": 0.8}
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


def test_classify_intent_defaults_calendar_read_range_to_today():
    settings = _settings()
    with patch("app.router.requests.post") as mock_post:
        mock_post.return_value = _groq_response(
            {"intent": "read_events", "target": "local", "specialist": "calendar_read", "confidence": 0.9}
        )
        result = classify_intent("cosa ho in programma", settings)

    assert result["date_range"] == "today"


def test_classify_intent_extracts_calendar_create_fields():
    settings = _settings()
    with patch("app.router.requests.post") as mock_post:
        mock_post.return_value = _groq_response(
            {
                "intent": "create_event",
                "target": "local",
                "specialist": "calendar_create",
                "event_title": "Dentista",
                "event_date": "2026-08-22",
                "event_time": "17:00",
                "confidence": 0.9,
            }
        )
        result = classify_intent("aggiungi appuntamento dal dentista venerdì alle 17", settings)

    assert result["event_title"] == "Dentista"
    assert result["event_date"] == "2026-08-22"
    assert result["event_time"] == "17:00"


def test_classify_image_message_always_targets_gemini():
    assert classify_image_message() == {
        "intent": "vision",
        "target": "gemini",
        "specialist": None,
        "city": None,
        "date_range": None,
        "event_title": None,
        "event_date": None,
        "event_time": None,
        "confidence": 1.0,
    }
