"""Test per la logica di dominio di conversazioni/messaggi (RF-001, RF-004)."""
from unittest.mock import patch

import pytest

from app.chat_service import ChatServiceError, get_or_create_conversation, process_message
from app.config import Settings
from tests.fake_supabase import FakeSupabaseClient


@pytest.fixture(autouse=True)
def _no_real_fact_extraction():
    """`extract_facts` (RF-013) farebbe una vera chiamata Groq se non mockata
    — qui è irrilevante per la maggior parte dei test di questo file, quindi
    la si disattiva di default. I test dedicati alla memoria la rimockano
    esplicitamente per verificarne il comportamento."""
    with patch("app.chat_service.extract_facts", return_value=[]):
        yield


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


def test_process_message_delegation_prompt_does_not_duplicate_current_message():
    """La cronologia passata a valle va recuperata *prima* di inserire il
    messaggio utente corrente, altrimenti finisce duplicata nel prompt
    (una volta come "contesto", una volta come "richiesta attuale") — bug
    scoperto durante la verifica dello specialist email_send, dove la stessa
    duplicazione arrivava a far rifiutare la risposta JSON di Groq."""
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={"intent": "coding", "target": "claude", "specialist": None, "confidence": 0.9},
    ):
        result = process_message(
            db, settings, text="scrivi uno script unico e riconoscibile", image_base64=None, conversation_id=None
        )

    assert result["action"]["prompt"].count("scrivi uno script unico e riconoscibile") == 1


def test_process_message_email_read_without_google_connected():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "read_inbox",
            "target": "local",
            "specialist": "email_read",
            "city": None,
            "confidence": 0.9,
        },
    ):
        result = process_message(
            db, settings, text="leggimi le email", image_base64=None, conversation_id=None
        )

    assert result["action"] is None
    assert result["assistant_message"]["action_type"] is None
    assert "Google non è collegato" in result["assistant_message"]["content"]


def test_process_message_email_read_lists_messages():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={"intent": "read_inbox", "target": "local", "specialist": "email_read", "confidence": 0.9},
    ), patch("app.chat_service.ensure_valid_access_token", return_value="at"), patch(
        "app.chat_service.list_messages",
        return_value=[{"from": "Marco", "subject": "Ciao", "snippet": "come va?"}],
    ):
        result = process_message(
            db, settings, text="leggimi le email", image_base64=None, conversation_id=None
        )

    assert "Marco" in result["assistant_message"]["content"]


def test_process_message_calendar_read_lists_events():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "read_events",
            "target": "local",
            "specialist": "calendar_read",
            "date_range": "tomorrow",
            "confidence": 0.9,
        },
    ), patch("app.chat_service.ensure_valid_access_token", return_value="at"), patch(
        "app.chat_service.list_events",
        return_value=[{"start": "2026-08-21T09:00:00", "summary": "Riunione", "location": ""}],
    ):
        result = process_message(
            db, settings, text="cosa ho domani", image_base64=None, conversation_id=None
        )

    assert "Riunione" in result["assistant_message"]["content"]


def test_process_message_calendar_create_builds_event():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "create_event",
            "target": "local",
            "specialist": "calendar_create",
            "event_title": "Dentista",
            "event_date": "2026-08-22",
            "event_time": "17:00",
            "confidence": 0.9,
        },
    ), patch("app.chat_service.ensure_valid_access_token", return_value="at"), patch(
        "app.chat_service.create_event", return_value="evt123"
    ) as mock_create:
        result = process_message(
            db, settings, text="aggiungi dentista venerdì alle 17", image_base64=None, conversation_id=None
        )

    assert "Dentista" in result["assistant_message"]["content"]
    assert "22/08/2026" in result["assistant_message"]["content"]
    mock_create.assert_called_once()


def test_process_message_email_send_without_recipient_asks_for_one():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "send_email",
            "target": "local",
            "specialist": "email_send",
            "email_to": None,
            "confidence": 0.7,
        },
    ):
        result = process_message(
            db, settings, text="manda una mail per dire che arrivo tardi", image_base64=None, conversation_id=None
        )

    assert result["action"] is None
    assert "A chi devo inviarla" in result["assistant_message"]["content"]


def test_process_message_email_send_without_google_connected():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "send_email",
            "target": "local",
            "specialist": "email_send",
            "email_to": "mario@esempio.com",
            "confidence": 0.9,
        },
    ), patch(
        "app.chat_service.compose_email",
        return_value={"subject": "Ritardo", "body": "Arrivo tardi."},
    ):
        result = process_message(
            db, settings, text="manda una mail a mario@esempio.com per dire che arrivo tardi",
            image_base64=None, conversation_id=None,
        )

    assert result["action"] is None
    assert "Google non è collegato" in result["assistant_message"]["content"]


def test_process_message_email_send_creates_draft_and_asks_confirmation():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "send_email",
            "target": "local",
            "specialist": "email_send",
            "email_to": "mario@esempio.com",
            "confidence": 0.9,
        },
    ), patch(
        "app.chat_service.compose_email",
        return_value={"subject": "Ritardo riunione", "body": "Ciao Mario, arrivo con 10 minuti di ritardo."},
    ), patch("app.chat_service.ensure_valid_access_token", return_value="at"), patch(
        "app.chat_service.create_draft", return_value="draft123"
    ) as mock_draft:
        result = process_message(
            db, settings, text="manda una mail a mario@esempio.com per dire che arrivo tardi",
            image_base64=None, conversation_id=None,
        )

    mock_draft.assert_called_once_with(
        "at", settings, to="mario@esempio.com", subject="Ritardo riunione",
        body="Ciao Mario, arrivo con 10 minuti di ritardo.",
    )
    assert result["action"] == {
        "type": "confirm_email_send",
        "draft_id": "draft123",
        "to": "mario@esempio.com",
        "subject": "Ritardo riunione",
        "body": "Ciao Mario, arrivo con 10 minuti di ritardo.",
    }
    assert result["assistant_message"]["action_type"] == "confirm_email_send"
    assert "Confermi l'invio?" in result["assistant_message"]["content"]


def test_process_message_calendar_create_without_title_asks_to_repeat():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "create_event",
            "target": "local",
            "specialist": "calendar_create",
            "event_title": None,
            "event_date": None,
            "event_time": "09:00",
            "confidence": 0.5,
        },
    ):
        result = process_message(
            db, settings, text="aggiungi un evento", image_base64=None, conversation_id=None
        )

    assert "ripetere" in result["assistant_message"]["content"]


def test_process_message_weather_specialist_uses_get_weather():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "weather_query",
            "target": "local",
            "specialist": "weather",
            "city": "Roma",
            "confidence": 0.9,
        },
    ), patch(
        "app.chat_service.get_weather",
        return_value={"city": "Roma", "temp": 27, "description": "cielo sereno"},
    ):
        result = process_message(
            db, settings, text="che tempo fa a Roma", image_base64=None, conversation_id=None
        )

    assert "Roma" in result["assistant_message"]["content"]
    assert "27" in result["assistant_message"]["content"]


def test_process_message_weather_specialist_without_city_asks_for_one():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "weather_query",
            "target": "local",
            "specialist": "weather",
            "city": None,
            "confidence": 0.9,
        },
    ):
        result = process_message(
            db, settings, text="che tempo fa", image_base64=None, conversation_id=None
        )

    assert "città" in result["assistant_message"]["content"]


def test_process_message_weather_specialist_handles_weather_error():
    from app.weather import WeatherError

    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "weather_query",
            "target": "local",
            "specialist": "weather",
            "city": "Roma",
            "confidence": 0.9,
        },
    ), patch("app.chat_service.get_weather", side_effect=WeatherError("città non trovata")):
        result = process_message(
            db, settings, text="che tempo fa a Roma", image_base64=None, conversation_id=None
        )

    assert "non disponibile" in result["assistant_message"]["content"]


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

    with patch("app.chat_service.classify_intent", side_effect=RouterError("boom")), patch(
        "app.chat_service.generate_reply", return_value="Risposta generica."
    ):
        result = process_message(
            db, settings, text="qualsiasi cosa", image_base64=None, conversation_id=None
        )

    assert result["assistant_message"]["target"] == "local"
    assert result["assistant_message"]["intent"] == "unknown"
    assert result["assistant_message"]["content"] == "Risposta generica."


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
    ), patch("app.chat_service.generate_reply", return_value="ok"):
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


def test_process_message_saves_extracted_facts_tied_to_user_message():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={"intent": "x", "target": "local", "specialist": "other", "confidence": 0.5},
    ), patch("app.chat_service.generate_reply", return_value="Piacere Marco."), patch(
        "app.chat_service.extract_facts",
        return_value=[{"category": "contact", "fact": "L'utente si chiama Marco", "confidence": 0.9}],
    ):
        result = process_message(
            db, settings, text="mi chiamo Marco", image_base64=None, conversation_id=None
        )

    saved_facts = db._store["user_facts"]
    assert len(saved_facts) == 1
    assert saved_facts[0]["fact"] == "L'utente si chiama Marco"
    assert saved_facts[0]["source_message_id"] == result["user_message"]["id"]


def test_process_message_passes_known_facts_to_general_chat():
    db = FakeSupabaseClient()
    settings = _settings()
    db.table("user_facts").insert(
        {"user_id": "default", "category": "preference", "fact": "Odia il caffè", "confidence": 0.9}
    ).execute()

    with patch(
        "app.chat_service.classify_intent",
        return_value={"intent": "x", "target": "local", "specialist": "other", "confidence": 0.5},
    ), patch("app.chat_service.extract_facts", return_value=[]), patch(
        "app.chat_service.generate_reply", return_value="ok"
    ) as mock_generate:
        process_message(db, settings, text="cosa mi consigli?", image_base64=None, conversation_id=None)

    known_facts_arg = mock_generate.call_args.kwargs["known_facts"]
    assert any(f["fact"] == "Odia il caffè" for f in known_facts_arg)


def test_process_message_no_facts_extracted_when_nothing_notable():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={"intent": "x", "target": "local", "specialist": "time", "confidence": 0.5},
    ), patch("app.chat_service.extract_facts", return_value=[]):
        process_message(db, settings, text="che ore sono?", image_base64=None, conversation_id=None)

    assert "user_facts" not in db._store or db._store["user_facts"] == []


def test_process_message_conversation_delete_removes_active_conversation():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={"intent": "x", "target": "local", "specialist": "other", "confidence": 0.5},
    ), patch("app.chat_service.generate_reply", return_value="ok"):
        first = process_message(
            db, settings, text="ciao", image_base64=None, conversation_id=None
        )
    conv_id = first["conversation_id"]

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "delete_chat",
            "target": "local",
            "specialist": "conversation_delete",
            "confidence": 0.9,
        },
    ):
        result = process_message(
            db, settings, text="cancella questa conversazione", image_base64=None, conversation_id=conv_id
        )

    assert result["conversation_id"] is None
    assert "elimino questa conversazione" in result["assistant_message"]["content"].lower()
    assert not any(c["id"] == conv_id for c in db._store["conversations"])
    assert not any(m["conversation_id"] == conv_id for m in db._store["messages"])


def test_process_message_conversation_delete_without_active_conversation():
    db = FakeSupabaseClient()
    settings = _settings()

    with patch(
        "app.chat_service.classify_intent",
        return_value={
            "intent": "delete_chat",
            "target": "local",
            "specialist": "conversation_delete",
            "confidence": 0.9,
        },
    ):
        result = process_message(
            db, settings, text="cancella questa conversazione", image_base64=None, conversation_id=None
        )

    assert result["conversation_id"] is not None  # non è stato eliminato nulla
    assert "seleziona" in result["assistant_message"]["content"].lower()
