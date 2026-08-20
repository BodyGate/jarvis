"""Test per la memoria a lungo termine (RF-013, tabella user_facts)."""
import json
from unittest.mock import Mock, patch

import requests

from app.config import Settings
from app.memory import delete_fact, extract_facts, get_known_facts, list_all_facts, save_facts
from tests.fake_supabase import FakeSupabaseClient


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


def _groq_response(payload: dict) -> Mock:
    mock = Mock()
    mock.raise_for_status = Mock()
    mock.json.return_value = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    return mock


def test_extract_facts_returns_parsed_facts():
    settings = _settings()
    with patch("app.memory.requests.post") as mock_post:
        mock_post.return_value = _groq_response(
            {"facts": [{"category": "preference", "fact": "Odia il caffè", "confidence": 0.9}]}
        )
        facts = extract_facts("odio il caffè", [], settings)

    assert facts == [{"category": "preference", "fact": "Odia il caffè", "confidence": 0.9}]


def test_extract_facts_returns_empty_for_operational_message():
    settings = _settings()
    with patch("app.memory.requests.post") as mock_post:
        mock_post.return_value = _groq_response({"facts": []})
        facts = extract_facts("che ore sono?", [], settings)

    assert facts == []


def test_extract_facts_drops_invalid_categories():
    settings = _settings()
    with patch("app.memory.requests.post") as mock_post:
        mock_post.return_value = _groq_response(
            {"facts": [{"category": "not-a-category", "fact": "qualcosa", "confidence": 0.9}]}
        )
        facts = extract_facts("qualcosa", [], settings)

    assert facts == []


def test_extract_facts_includes_known_facts_in_prompt():
    settings = _settings()
    known = [{"category": "contact", "fact": "Marco è il capo", "confidence": 1.0}]
    with patch("app.memory.requests.post") as mock_post:
        mock_post.return_value = _groq_response({"facts": []})
        extract_facts("qualcosa", known, settings)

    sent_system = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "Marco è il capo" in sent_system


def test_extract_facts_returns_empty_without_text():
    settings = _settings()
    with patch("app.memory.requests.post") as mock_post:
        facts = extract_facts("", [], settings)

    assert facts == []
    mock_post.assert_not_called()


def test_extract_facts_returns_empty_without_api_key():
    settings = _settings(groq_api_key=None)
    facts = extract_facts("odio il caffè", [], settings)
    assert facts == []


def test_extract_facts_returns_empty_on_network_error_never_raises():
    settings = _settings()
    with patch("app.memory.requests.post", side_effect=requests.ConnectionError("boom")):
        facts = extract_facts("odio il caffè", [], settings)

    assert facts == []


def test_extract_facts_returns_empty_on_malformed_json():
    settings = _settings()
    with patch("app.memory.requests.post") as mock_post:
        mock = Mock()
        mock.raise_for_status = Mock()
        mock.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
        mock_post.return_value = mock
        facts = extract_facts("odio il caffè", [], settings)

    assert facts == []


def test_save_and_get_known_facts_roundtrip():
    db = FakeSupabaseClient()
    save_facts(
        db,
        [{"category": "preference", "fact": "Odia il caffè", "confidence": 0.9}],
        source_message_id="msg-1",
    )
    facts = get_known_facts(db)

    assert len(facts) == 1
    assert facts[0]["fact"] == "Odia il caffè"


def test_get_known_facts_returns_empty_when_none_saved():
    db = FakeSupabaseClient()
    assert get_known_facts(db) == []


def test_list_all_facts_includes_id_for_management():
    db = FakeSupabaseClient()
    save_facts(db, [{"category": "habit", "fact": "Corre ogni mattina", "confidence": 0.8}], source_message_id=None)

    facts = list_all_facts(db)

    assert len(facts) == 1
    assert "id" in facts[0]
    assert facts[0]["fact"] == "Corre ogni mattina"


def test_delete_fact_removes_it():
    db = FakeSupabaseClient()
    save_facts(db, [{"category": "habit", "fact": "Corre ogni mattina", "confidence": 0.8}], source_message_id=None)
    fact_id = list_all_facts(db)[0]["id"]

    result = delete_fact(db, fact_id)

    assert result is True
    assert list_all_facts(db) == []


def test_delete_fact_returns_false_for_unknown_id():
    db = FakeSupabaseClient()
    assert delete_fact(db, "does-not-exist") is False
