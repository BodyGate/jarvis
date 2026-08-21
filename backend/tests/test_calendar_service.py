"""Test per l'integrazione Google Calendar (app.calendar_service)."""
from unittest.mock import Mock, patch

import pytest
import requests

from app.calendar_service import CalendarError, create_event, delete_event, list_events
from app.config import Settings


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


def test_list_events_maps_fields():
    settings = _settings()
    resp = _resp(
        {
            "items": [
                {
                    "id": "e1",
                    "summary": "Riunione",
                    "location": "Zoom",
                    "start": {"dateTime": "2026-08-21T09:00:00+02:00"},
                    "end": {"dateTime": "2026-08-21T10:00:00+02:00"},
                }
            ]
        }
    )
    with patch("app.calendar_service.requests.get", return_value=resp):
        events = list_events("token", settings, "2026-08-21T00:00:00Z", "2026-08-22T00:00:00Z")

    assert events == [
        {
            "id": "e1",
            "summary": "Riunione",
            "description": "",
            "location": "Zoom",
            "start": "2026-08-21T09:00:00+02:00",
            "end": "2026-08-21T10:00:00+02:00",
        }
    ]


def test_list_events_handles_all_day_events():
    settings = _settings()
    resp = _resp({"items": [{"id": "e1", "start": {"date": "2026-08-21"}, "end": {"date": "2026-08-22"}}]})
    with patch("app.calendar_service.requests.get", return_value=resp):
        events = list_events("token", settings, "2026-08-21T00:00:00Z", "2026-08-22T00:00:00Z")

    assert events[0]["start"] == "2026-08-21"


def test_list_events_raises_on_network_error():
    settings = _settings()
    with patch("app.calendar_service.requests.get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(CalendarError):
            list_events("token", settings, "a", "b")


def test_create_event_returns_id():
    settings = _settings()
    resp = _resp({"id": "evt-1"})
    with patch("app.calendar_service.requests.post", return_value=resp) as mock_post:
        event_id = create_event(
            "token", settings, summary="Dentista", start="2026-08-22T17:00:00", end="2026-08-22T18:00:00"
        )

    assert event_id == "evt-1"
    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["summary"] == "Dentista"
    assert sent_json["start"] == {"dateTime": "2026-08-22T17:00:00", "timeZone": "UTC"}


def test_create_event_respects_explicit_timezone_offset():
    settings = _settings()
    resp = _resp({"id": "evt-2"})
    with patch("app.calendar_service.requests.post", return_value=resp) as mock_post:
        create_event(
            "token",
            settings,
            summary="X",
            start="2026-08-22T17:00:00+02:00",
            end="2026-08-22T18:00:00+02:00",
        )

    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["start"] == {"dateTime": "2026-08-22T17:00:00+02:00"}


def test_create_event_uses_date_field_for_all_day_events():
    """Un evento "tutto il giorno" (data senza orario) va rappresentato con
    il campo `date`, non `dateTime` + timeZone — altrimenti l'API Calendar
    rifiuta la richiesta come malformata."""
    settings = _settings()
    resp = _resp({"id": "evt-3"})
    with patch("app.calendar_service.requests.post", return_value=resp) as mock_post:
        create_event("token", settings, summary="Compleanno", start="2026-08-22", end="2026-08-23")

    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["start"] == {"date": "2026-08-22"}
    assert sent_json["end"] == {"date": "2026-08-23"}


def test_create_event_raises_on_network_error():
    settings = _settings()
    with patch("app.calendar_service.requests.post", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(CalendarError):
            create_event("token", settings, summary="X", start="a", end="b")


def test_delete_event_succeeds_on_204():
    settings = _settings()
    resp = Mock(status_code=204)
    with patch("app.calendar_service.requests.delete", return_value=resp):
        delete_event("token", "evt-1", settings)  # non deve sollevare


def test_delete_event_treats_404_as_success():
    settings = _settings()
    resp = Mock(status_code=404)
    with patch("app.calendar_service.requests.delete", return_value=resp):
        delete_event("token", "evt-1", settings)  # già cancellato, non deve sollevare


def test_delete_event_raises_on_server_error():
    settings = _settings()
    resp = Mock(status_code=500)
    resp.raise_for_status.side_effect = requests.HTTPError("500")
    with patch("app.calendar_service.requests.delete", return_value=resp):
        with pytest.raises(CalendarError):
            delete_event("token", "evt-1", settings)
