"""Test per l'autenticazione applicativa (ADR-0002) e il rate limiting
(ADR-0005) sulle route sotto /api/session."""
from werkzeug.security import generate_password_hash

from app import create_app


def _make_app(tmp_path, password_hash="", secret_key="test-secret"):
    env_file = tmp_path / ".env"
    lines = [f"SECRET_KEY={secret_key}"]
    if password_hash:
        lines.append(f"APP_PASSWORD_HASH={password_hash}")
    env_file.write_text("\n".join(lines), encoding="utf-8")
    app = create_app(env_file=str(env_file))
    app.config["TESTING"] = True
    return app


def test_login_fails_when_password_not_configured(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()

    response = client.post("/api/session/login", json={"password": "anything"})

    assert response.status_code == 503
    assert response.get_json()["error"] == "app_password_not_configured"


def test_login_rejects_wrong_password(tmp_path):
    app = _make_app(tmp_path, password_hash=generate_password_hash("correct-horse"))
    client = app.test_client()

    response = client.post("/api/session/login", json={"password": "wrong"})

    assert response.status_code == 401
    assert response.get_json()["error"] == "invalid_password"


def test_login_accepts_correct_password_and_sets_session(tmp_path):
    app = _make_app(tmp_path, password_hash=generate_password_hash("correct-horse"))
    client = app.test_client()

    login_response = client.post("/api/session/login", json={"password": "correct-horse"})
    assert login_response.status_code == 200
    assert login_response.get_json()["success"] is True

    status_response = client.get("/api/session/status")
    assert status_response.get_json()["data"]["authenticated"] is True


def test_protected_endpoint_rejected_without_session(tmp_path):
    app = _make_app(tmp_path, password_hash=generate_password_hash("correct-horse"))
    client = app.test_client()

    response = client.get("/api/chat/conversations")

    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"


def test_health_and_login_are_public(tmp_path):
    app = _make_app(tmp_path, password_hash=generate_password_hash("correct-horse"))
    client = app.test_client()

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/session/status").status_code == 200


def test_logout_clears_session(tmp_path):
    app = _make_app(tmp_path, password_hash=generate_password_hash("correct-horse"))
    client = app.test_client()

    client.post("/api/session/login", json={"password": "correct-horse"})
    client.post("/api/session/logout")

    response = client.get("/api/chat/conversations")
    assert response.status_code == 401


def test_login_rate_limited_after_five_attempts(tmp_path):
    app = _make_app(tmp_path, password_hash=generate_password_hash("correct-horse"))
    client = app.test_client()

    for _ in range(5):
        response = client.post("/api/session/login", json={"password": "wrong"})
        assert response.status_code == 401

    response = client.post("/api/session/login", json={"password": "wrong"})
    assert response.status_code == 429
