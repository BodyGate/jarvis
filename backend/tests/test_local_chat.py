"""Test per la risposta locale generica (RF-003, specialist "other")."""
from unittest.mock import Mock, patch

import pytest
import requests

from app.config import Settings
from app.local_chat import LocalChatError, generate_reply


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


def _groq_response(text: str) -> Mock:
    mock = Mock()
    mock.raise_for_status = Mock()
    mock.json.return_value = {"choices": [{"message": {"content": text}}]}
    return mock


def test_generate_reply_returns_text():
    settings = _settings()
    with patch("app.local_chat.requests.post") as mock_post:
        mock_post.return_value = _groq_response("Ciao! Sono JARVIS, il tuo assistente personale.")
        result = generate_reply("presentati", [], settings)

    assert result == "Ciao! Sono JARVIS, il tuo assistente personale."


def test_generate_reply_includes_context_in_messages():
    settings = _settings()
    context = [{"role": "user", "content": "mi chiamo Marco"}, {"role": "assistant", "content": "Piacere Marco"}]
    with patch("app.local_chat.requests.post") as mock_post:
        mock_post.return_value = _groq_response("Certo, Marco.")
        generate_reply("come mi chiamo?", context, settings)

    sent_messages = mock_post.call_args.kwargs["json"]["messages"]
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[1] == {"role": "user", "content": "mi chiamo Marco"}
    assert sent_messages[2] == {"role": "assistant", "content": "Piacere Marco"}
    assert sent_messages[-1] == {"role": "user", "content": "come mi chiamo?"}


def test_generate_reply_includes_known_facts_in_system_prompt():
    settings = _settings()
    known_facts = [{"category": "preference", "fact": "Odia il caffè", "confidence": 0.9}]
    with patch("app.local_chat.requests.post") as mock_post:
        mock_post.return_value = _groq_response("ok")
        generate_reply("cosa mi consigli per colazione?", [], settings, known_facts=known_facts)

    system_prompt = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "Odia il caffè" in system_prompt


def test_generate_reply_without_known_facts_has_no_facts_section():
    settings = _settings()
    with patch("app.local_chat.requests.post") as mock_post:
        mock_post.return_value = _groq_response("ok")
        generate_reply("ciao", [], settings)

    system_prompt = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "sai già su questo utente" not in system_prompt


def test_generate_reply_raises_without_api_key():
    settings = _settings(groq_api_key=None)
    with pytest.raises(LocalChatError):
        generate_reply("ciao", [], settings)


def test_generate_reply_raises_on_network_error():
    settings = _settings()
    with patch("app.local_chat.requests.post", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(LocalChatError):
            generate_reply("ciao", [], settings)


def test_generate_reply_raises_on_malformed_response():
    settings = _settings()
    with patch("app.local_chat.requests.post") as mock_post:
        mock = Mock()
        mock.raise_for_status = Mock()
        mock.json.return_value = {"choices": []}
        mock_post.return_value = mock
        with pytest.raises(LocalChatError):
            generate_reply("ciao", [], settings)
