"""Test per l'integrazione Gmail (app.gmail)."""
import base64
from unittest.mock import Mock, patch

import pytest
import requests

from app.config import Settings
from app.gmail import GmailError, create_draft, get_message, list_messages, send_draft


def _settings():
    return Settings(
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
        token_encryption_key=None,
        external_service_timeout_seconds=5,
    )


def _resp(json_data, status_code=200):
    mock = Mock()
    mock.status_code = status_code
    mock.raise_for_status = Mock()
    mock.json.return_value = json_data
    return mock


def test_list_messages_fetches_metadata_for_each_id():
    settings = _settings()
    list_resp = _resp({"messages": [{"id": "m1"}, {"id": "m2"}]})
    detail_resp = _resp(
        {
            "id": "m1",
            "threadId": "t1",
            "snippet": "ciao",
            "payload": {"headers": [{"name": "From", "value": "marco@example.com"}, {"name": "Subject", "value": "Ciao"}]},
        }
    )
    with patch("app.gmail.requests.get", side_effect=[list_resp, detail_resp, detail_resp]):
        results = list_messages("token", settings, max_results=2)

    assert len(results) == 2
    assert results[0]["from"] == "marco@example.com"
    assert results[0]["subject"] == "Ciao"


def test_list_messages_raises_gmail_error_on_network_failure():
    settings = _settings()
    with patch("app.gmail.requests.get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(GmailError):
            list_messages("token", settings)


def test_get_message_extracts_plain_text_body():
    settings = _settings()
    body_text = "Ciao, come stai?"
    encoded_body = base64.urlsafe_b64encode(body_text.encode("utf-8")).decode("ascii").rstrip("=")
    detail_resp = _resp(
        {
            "id": "m1",
            "threadId": "t1",
            "snippet": "ciao",
            "payload": {
                "mimeType": "text/plain",
                "body": {"data": encoded_body},
                "headers": [
                    {"name": "From", "value": "marco@example.com"},
                    {"name": "Subject", "value": "Ciao"},
                    {"name": "Message-ID", "value": "<abc@mail.gmail.com>"},
                ],
            },
        }
    )
    with patch("app.gmail.requests.get", return_value=detail_resp):
        message = get_message("token", "m1", settings)

    assert message["body"] == body_text
    assert message["message_id_header"] == "<abc@mail.gmail.com>"


def test_get_message_extracts_body_from_multipart():
    settings = _settings()
    body_text = "Corpo del messaggio"
    encoded_body = base64.urlsafe_b64encode(body_text.encode("utf-8")).decode("ascii").rstrip("=")
    detail_resp = _resp(
        {
            "id": "m1",
            "threadId": "t1",
            "snippet": "",
            "payload": {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": encoded_body}},
                    {"mimeType": "text/html", "body": {"data": "aGVsbG8="}},
                ],
                "headers": [],
            },
        }
    )
    with patch("app.gmail.requests.get", return_value=detail_resp):
        message = get_message("token", "m1", settings)

    assert message["body"] == body_text


def test_create_draft_without_reply_encodes_mime():
    settings = _settings()
    draft_resp = _resp({"id": "draft-1"})
    with patch("app.gmail.requests.post", return_value=draft_resp) as mock_post:
        draft_id = create_draft(
            "token", settings, to="dest@example.com", subject="Oggetto", body="Testo del messaggio"
        )

    assert draft_id == "draft-1"
    sent_json = mock_post.call_args.kwargs["json"]
    assert "threadId" not in sent_json["message"]
    raw_decoded = base64.urlsafe_b64decode(sent_json["message"]["raw"] + "===").decode("utf-8")
    assert "dest@example.com" in raw_decoded
    assert "Oggetto" in raw_decoded


def test_create_draft_with_reply_sets_thread_and_headers():
    settings = _settings()
    original_detail = _resp(
        {
            "id": "orig-1",
            "threadId": "thread-1",
            "snippet": "",
            "payload": {"headers": [{"name": "Message-ID", "value": "<orig@mail.gmail.com>"}]},
        }
    )
    draft_resp = _resp({"id": "draft-2"})
    with patch("app.gmail.requests.get", return_value=original_detail), patch(
        "app.gmail.requests.post", return_value=draft_resp
    ) as mock_post:
        draft_id = create_draft(
            "token",
            settings,
            to="dest@example.com",
            subject="Re: Oggetto",
            body="Risposta",
            reply_to_message_id="orig-1",
        )

    assert draft_id == "draft-2"
    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["message"]["threadId"] == "thread-1"
    raw_decoded = base64.urlsafe_b64decode(sent_json["message"]["raw"] + "===").decode("utf-8")
    assert "orig@mail.gmail.com" in raw_decoded


def test_send_draft_returns_message_id():
    settings = _settings()
    send_resp = _resp({"id": "sent-1"})
    with patch("app.gmail.requests.post", return_value=send_resp):
        message_id = send_draft("token", "draft-1", settings)

    assert message_id == "sent-1"


def test_send_draft_raises_on_error():
    settings = _settings()
    with patch("app.gmail.requests.post", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(GmailError):
            send_draft("token", "draft-1", settings)
