"""Test per gli endpoint calendario (sezione 9.1, RF-009, RF-010)."""
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import create_app
from app.google_oauth import GoogleOAuthError


def _logged_in_client(tmp_path):
    env_file = tmp_path / ".env"
    password_hash = generate_password_hash("correct-horse")
    env_file.write_text(f"SECRET_KEY=test-secret\nAPP_PASSWORD_HASH={password_hash}\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    app.config["TESTING"] = True
    client = app.test_client()
    client.post("/api/session/login", json={"password": "correct-horse"})
    return client


def test_events_requires_session(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    client = app.test_client()

    assert client.get("/api/calendar/events").status_code == 401


def test_events_requires_time_range(tmp_path):
    client = _logged_in_client(tmp_path)

    response = client.get("/api/calendar/events")

    assert response.status_code == 400


def test_events_returns_data(tmp_path):
    client = _logged_in_client(tmp_path)

    with patch("app.calendar_routes._access_token", return_value="at"), patch(
        "app.calendar_routes.list_events", return_value=[{"id": "1", "summary": "Riunione"}]
    ):
        response = client.get(
            "/api/calendar/events?time_min=2026-08-20T00:00:00Z&time_max=2026-08-21T00:00:00Z"
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["events"][0]["summary"] == "Riunione"


def test_events_reports_not_connected(tmp_path):
    client = _logged_in_client(tmp_path)

    with patch("app.calendar_routes._access_token", side_effect=GoogleOAuthError("non collegato")):
        response = client.get(
            "/api/calendar/events?time_min=2026-08-20T00:00:00Z&time_max=2026-08-21T00:00:00Z"
        )

    assert response.status_code == 503


def test_create_event_requires_fields(tmp_path):
    client = _logged_in_client(tmp_path)

    response = client.post("/api/calendar/event", json={"summary": "Solo titolo"})

    assert response.status_code == 400


def test_create_event_returns_event_id(tmp_path):
    client = _logged_in_client(tmp_path)

    with patch("app.calendar_routes._access_token", return_value="at"), patch(
        "app.calendar_routes.create_event", return_value="evt-789"
    ):
        response = client.post(
            "/api/calendar/event",
            json={"summary": "Dentista", "start": "2026-08-22T17:00:00", "end": "2026-08-22T18:00:00"},
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["event_id"] == "evt-789"


def test_delete_event_returns_success(tmp_path):
    client = _logged_in_client(tmp_path)

    with patch("app.calendar_routes._access_token", return_value="at"), patch(
        "app.calendar_routes.delete_event"
    ) as mock_delete:
        response = client.delete("/api/calendar/event/evt-789")

    assert response.status_code == 200
    mock_delete.assert_called_once()
