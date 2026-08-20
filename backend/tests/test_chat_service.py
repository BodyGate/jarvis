"""Test per la logica di dominio di conversazioni/messaggi (RF-001, RF-004)."""
from unittest.mock import patch

import pytest

from app.chat_service import ChatServiceError, get_or_create_conversation, process_message
from app.config import Settings
from tests.fake_supabase import FakeSupabaseClient


def _settings():
    return Settings(
        flask_env="development",
        secret_key="s",
        app_password_hash=None,
        supabase_url=None,
        supabase_key=None,
        database_url=None,
        groq_api_key="test-key",
        gemini_api_key=None,
        openweather_api_key=None,
        google_client_id=None,
        google_client_secret=None,
        google_redirect_uri=None,
        token_encryption_key=None,
        external_service_timeout_seconds=5,
    )


def test_get_or_create_conversation_creates_new_when_no_id():
    db = FakeSupabaseClient()
    conv = get_or_create_conversation(db, None, "Ciao JARVIS come stai oggi")
    assert conv["title"] == "Ciao JARVIS come stai oggi"
    assert conv["user_id"] == "default"


def test_get_or_create_conversation_raises_for_unknown_id():
    db = FakeSupabaseClient()
    with pytest.raises(ChatServiceError):
        get_or_create_conversation(db, "does-not-exist", "testo")


def test_process_message_delegation_target_builds_copy_and_open_action():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={"intent": "coding", "target": "claude", "specialist": None, "confidence": 0.9},
    ):
        result = process_message(
            db, settings, text="scrivi uno script", image_base64=None, conversation_id=None
        )

    assert result["action"]["type"] == "copy_and_open"
    assert result["action"]["target"] == "claude"
    assert result["action"]["url"] == "https://claude.ai/new"
    assert "scrivi uno script" in result["action"]["prompt"]
    assert result["assistant_message"]["action_type"] == "copy_and_open"


def test_process_message_local_target_has_no_action():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "weather_query",
            "target": "local",
            "specialist": "weather",
            "confidence": 0.9,
        },
    ):
        result = process_message(
            db, settings, text="che tempo fa", image_base64=None, conversation_id=None
        )

    assert result["action"] is None
    assert result["assistant_message"]["action_type"] is None
    assert "meteo" in result["assistant_message"]["content"]


def test_process_message_time_specialist_answers_directly():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={"intent": "what_time", "target": "local", "specialist": "time", "confidence": 0.9},
    ):
        result = process_message(
            db, settings, text="che ore sono", image_base64=None, conversation_id=None
        )

    assert "Sono le" in result["assistant_message"]["content"]


def test_process_message_search_specialist_uses_web_search():
    db = FakeSupabaseClient()
    settings = _settings()

    fake_results = [{"title": "T1", "snippet": "S1", "url": "https://example.com"}]
    with patch(
        "app.chat_service.classify_intent",
        return_value={"intent": "web_search", "target": "local", "specialist": "search", "confidence": 0.9},
    ), patch("app.chat_service.web_search", return_value=fake_results):
        result = process_message(
            db, settings, text="cerca notizie SpaceX", image_base64=None, conversation_id=None
        )

    assert "T1" in result["assistant_message"]["content"]
    assert "https://example.com" in result["assistant_message"]["content"]


def test_process_message_search_specialist_handles_search_error():
    from app.search import SearchError

    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={"intent": "web_search", "target": "local", "specialist": "search", "confidence": 0.9},
    ), patch("app.chat_service.web_search", side_effect=SearchError("rate limited")):
        result = process_message(
            db, settings, text="cerca notizie SpaceX", image_base64=None, conversation_id=None
        )

    assert "non disponibile" in result["assistant_message"]["content"]


def test_process_message_image_uses_vision():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch("app.chat_service.analyze_image", return_value="È una fattura Enel di 50 euro."):
        result = process_message(
            db, settings, text="", image_base64="ZmFrZS1pbWFnZQ==", conversation_id=None
        )

    assert result["assistant_message"]["target"] == "gemini"
    assert "fattura" in result["assistant_message"]["content"]
    assert result["action"] is None


def test_process_message_image_handles_vision_error():
    from app.vision import VisionError

    db = FakeSupabaseClient()
    settings = _settings()

    with patch("app.chat_service.analyze_image", side_effect=VisionError("quota esaurita")):
        result = process_message(
            db, settings, text="", image_base64="ZmFrZS1pbWFnZQ==", conversation_id=None
        )

    assert "Non sono riuscito" in result["assistant_message"]["content"]


def test_process_message_router_error_falls_back_to_local():
    from app.router import RouterError

    db = FakeSupabaseClient()
    settings = _settings()

    with patch("app.chat_service.classify_intent", side_effect=RouterError("boom")):
        result = process_message(
            db, settings, text="qualsiasi cosa", image_base64=None, conversation_id=None
        )

    assert result["assistant_message"]["target"] == "local"
    assert result["assistant_message"]["intent"] == "unknown"


def test_process_message_rejects_empty_input():
    db = FakeSupabaseClient()
    settings = _settings()

    with pytest.raises(ChatServiceError):
        process_message(db, settings, text="", image_base64=None, conversation_id=None)


def test_process_message_reuses_existing_conversation():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={"intent": "x", "target": "local", "confidence": 0.5},
    ):
        first = process_message(
            db, settings, text="primo messaggio", image_base64=None, conversation_id=None
        )
        second = process_message(
            db,
            settings,
            text="secondo messaggio",
            image_base64=None,
            conversation_id=first["conversation_id"],
        )

    assert first["conversation_id"] == second["conversation_id"]
    assert len(db._store["messages"]) == 4  # 2 user + 2 assistant
