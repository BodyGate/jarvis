"""Test per il flusso OAuth Google (sezione 9.1, ADR-0006)."""
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import create_app


def _logged_in_client(tmp_path):
    env_file = tmp_path / ".env"
    password_hash = generate_password_hash("correct-horse")
    env_file.write_text(
        f"SECRET_KEY=test-secret\nAPP_PASSWORD_HASH={password_hash}\n"
        "GOOGLE_CLIENT_ID=test-client-id\nGOOGLE_CLIENT_SECRET=test-secret-id\n"
        "GOOGLE_REDIRECT_URI=http://localhost:5000/auth/callback\n",
        encoding="utf-8",
    )
    app = create_app(env_file=str(env_file))
    app.config["TESTING"] = True
    client = app.test_client()
    client.post("/api/session/login", json={"password": "correct-horse"})
    return client


def test_google_start_requires_session(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    client = app.test_client()

    response = client.get("/auth/google")

    assert response.status_code == 401


def test_google_start_redirects_and_sets_state_cookie(tmp_path):
    client = _logged_in_client(tmp_path)

    response = client.get("/auth/google")

    assert response.status_code == 302
    assert "accounts.google.com" in response.headers["Location"]
    assert "oauth_state" in response.headers.get("Set-Cookie", "")


def test_callback_rejects_mismatched_state(tmp_path):
    client = _logged_in_client(tmp_path)
    client.set_cookie("oauth_state", "expected-state")

    response = client.get("/auth/callback?state=wrong-state&code=abc")

    assert response.status_code == 302
    assert "google=error" in response.headers["Location"]


def test_callback_rejects_missing_state_cookie(tmp_path):
    client = _logged_in_client(tmp_path)

    response = client.get("/auth/callback?state=some-state&code=abc")

    assert response.status_code == 302
    assert "google=error" in response.headers["Location"]


def test_callback_does_not_require_jarvis_session(tmp_path):
    """Fondamentale per ADR-0006: il callback di Google arriva senza il
    cookie di sessione Strict, deve comunque poter procedere se lo state combacia."""
    env_file = tmp_path / ".env"
    password_hash = generate_password_hash("correct-horse")
    env_file.write_text(
        f"SECRET_KEY=test-secret\nAPP_PASSWORD_HASH={password_hash}\n"
        "GOOGLE_CLIENT_ID=test-client-id\nGOOGLE_CLIENT_SECRET=test-secret-id\n"
        "GOOGLE_REDIRECT_URI=http://localhost:5000/auth/callback\n",
        encoding="utf-8",
    )
    app = create_app(env_file=str(env_file))
    client = app.test_client()  # nessun login
    client.set_cookie("oauth_state", "matching-state")

    with patch("app.google_auth_routes.exchange_code", return_value={"access_token": "at"}), patch(
        "app.google_auth_routes.save_tokens"
    ), patch("app.google_auth_routes.get_supabase_client"):
        response = client.get("/auth/callback?state=matching-state&code=abc")

    assert response.status_code == 302
    assert "google=connected" in response.headers["Location"]


def test_status_requires_session(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    client = app.test_client()

    assert client.get("/auth/status").status_code == 401


def test_status_reports_not_connected(tmp_path):
    client = _logged_in_client(tmp_path)

    with patch("app.google_auth_routes.get_tokens", return_value=None), patch(
        "app.google_auth_routes.get_supabase_client"
    ):
        response = client.get("/auth/status")

    assert response.get_json()["data"]["connected"] is False


def test_revoke_deletes_tokens(tmp_path):
    client = _logged_in_client(tmp_path)

    with patch(
        "app.google_auth_routes.get_tokens",
        return_value={"access_token": "at", "refresh_token": "rt", "expires_at": None, "scopes": []},
    ), patch("app.google_auth_routes.revoke_token") as mock_revoke, patch(
        "app.google_auth_routes.delete_tokens"
    ) as mock_delete, patch("app.google_auth_routes.get_supabase_client"):
        response = client.post("/auth/revoke")

    assert response.get_json()["success"] is True
    mock_revoke.assert_called_once()
    mock_delete.assert_called_once()
