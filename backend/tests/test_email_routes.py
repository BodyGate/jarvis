"""Test per gli endpoint email (sezione 9.1, RF-005→RF-008)."""
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


def test_list_emails_requires_session(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    client = app.test_client()

    assert client.get("/api/email/list").status_code == 401


def test_list_emails_returns_data(tmp_path):
    client = _logged_in_client(tmp_path)

    with patch("app.email_routes._access_token", return_value="at"), patch(
        "app.email_routes.list_messages", return_value=[{"id": "1", "subject": "Ciao"}]
    ):
        response = client.get("/api/email/list")

    assert response.status_code == 200
    assert response.get_json()["data"]["emails"][0]["subject"] == "Ciao"


def test_list_emails_reports_not_connected(tmp_path):
    client = _logged_in_client(tmp_path)

    with patch("app.email_routes._access_token", side_effect=GoogleOAuthError("non collegato")):
        response = client.get("/api/email/list")

    assert response.status_code == 503


def test_search_emails_requires_query(tmp_path):
    client = _logged_in_client(tmp_path)

    response = client.get("/api/email/search")

    assert response.status_code == 400


def test_draft_email_requires_fields(tmp_path):
    client = _logged_in_client(tmp_path)

    response = client.post("/api/email/draft", json={"to": "a@b.com"})

    assert response.status_code == 400


def test_draft_email_returns_draft_id(tmp_path):
    client = _logged_in_client(tmp_path)

    with patch("app.email_routes._access_token", return_value="at"), patch(
        "app.email_routes.create_draft", return_value="draft-123"
    ):
        response = client.post(
            "/api/email/draft", json={"to": "a@b.com", "subject": "Ciao", "body": "testo"}
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["draft_id"] == "draft-123"


def test_send_email_requires_draft_id(tmp_path):
    client = _logged_in_client(tmp_path)

    response = client.post("/api/email/send", json={})

    assert response.status_code == 400


def test_send_email_returns_message_id(tmp_path):
    client = _logged_in_client(tmp_path)

    with patch("app.email_routes._access_token", return_value="at"), patch(
        "app.email_routes.send_draft", return_value="msg-456"
    ):
        response = client.post("/api/email/send", json={"draft_id": "draft-123"})

    assert response.status_code == 200
    assert response.get_json()["data"]["message_id"] == "msg-456"
