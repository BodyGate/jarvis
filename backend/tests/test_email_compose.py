"""Test per la composizione del testo email (specialist "email_send", RF-007)."""
import json
from unittest.mock import Mock, patch

import pytest
import requests

from app.config import Settings
from app.email_compose import EmailComposeError, compose_email


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


def _groq_response(data: dict) -> Mock:
    mock = Mock()
    mock.raise_for_status = Mock()
    mock.json.return_value = {"choices": [{"message": {"content": json.dumps(data)}}]}
    return mock


def test_compose_email_returns_subject_and_body():
    settings = _settings()
    with patch("app.email_compose.requests.post") as mock_post:
        mock_post.return_value = _groq_response(
            {"subject": "Ritardo riunione", "body": "Ciao Mario, arriverò con 10 minuti di ritardo."}
        )
        result = compose_email("manda una mail a Mario per dirgli che arrivo tardi", [], settings)

    assert result == {"subject": "Ritardo riunione", "body": "Ciao Mario, arriverò con 10 minuti di ritardo."}


def test_compose_email_includes_context_in_messages():
    settings = _settings()
    context = [{"role": "user", "content": "sto organizzando una cena con Marco"}]
    with patch("app.email_compose.requests.post") as mock_post:
        mock_post.return_value = _groq_response({"subject": "Cena", "body": "Ci vediamo alle 20."})
        compose_email("scrivi l'invito", context, settings)

    sent_messages = mock_post.call_args.kwargs["json"]["messages"]
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[1] == {"role": "user", "content": "sto organizzando una cena con Marco"}
    assert sent_messages[-1] == {"role": "user", "content": "scrivi l'invito"}


def test_compose_email_raises_without_api_key():
    settings = _settings(groq_api_key=None)
    with pytest.raises(EmailComposeError):
        compose_email("scrivi una mail", [], settings)


def test_compose_email_raises_on_network_error():
    settings = _settings()
    with patch("app.email_compose.requests.post", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(EmailComposeError):
            compose_email("scrivi una mail", [], settings)


def test_compose_email_raises_on_malformed_response():
    settings = _settings()
    with patch("app.email_compose.requests.post") as mock_post:
        mock = Mock()
        mock.raise_for_status = Mock()
        mock.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
        mock_post.return_value = mock
        with pytest.raises(EmailComposeError):
            compose_email("scrivi una mail", [], settings)


def test_compose_email_raises_on_empty_subject_or_body():
    settings = _settings()
    with patch("app.email_compose.requests.post") as mock_post:
        mock_post.return_value = _groq_response({"subject": "", "body": "testo"})
        with pytest.raises(EmailComposeError):
            compose_email("scrivi una mail", [], settings)


def test_compose_email_retries_after_transient_refusal():
    """Il modello a volte rifiuta di generare JSON valido in modo non
    deterministico (verificato contro Groq reale) — un fallimento isolato
    non deve far fallire subito la richiesta."""
    settings = _settings()
    refusal = Mock()
    refusal.raise_for_status = Mock(side_effect=requests.HTTPError("400 Bad Request"))
    success = _groq_response({"subject": "Prova", "body": "Corpo di prova."})

    with patch("app.email_compose.requests.post", side_effect=[refusal, success]) as mock_post:
        result = compose_email("scrivi una mail di prova", [], settings)

    assert result == {"subject": "Prova", "body": "Corpo di prova."}
    assert mock_post.call_count == 2


def test_compose_email_gives_up_after_max_attempts():
    settings = _settings()
    refusal = Mock()
    refusal.raise_for_status = Mock(side_effect=requests.HTTPError("400 Bad Request"))

    with patch("app.email_compose.requests.post", return_value=refusal) as mock_post:
        with pytest.raises(EmailComposeError):
            compose_email("scrivi una mail di prova", [], settings)

    assert mock_post.call_count == 4
