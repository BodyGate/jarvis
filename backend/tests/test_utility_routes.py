"""Test per l'endpoint GET /api/weather (sezione 9.1, tabella Utility)."""
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import create_app


def _logged_in_client(tmp_path):
    env_file = tmp_path / ".env"
    password_hash = generate_password_hash("correct-horse")
    env_file.write_text(
        f"SECRET_KEY=test-secret\nAPP_PASSWORD_HASH={password_hash}\n", encoding="utf-8"
    )
    app = create_app(env_file=str(env_file))
    app.config["TESTING"] = True
    client = app.test_client()
    client.post("/api/session/login", json={"password": "correct-horse"})
    return client


def test_weather_endpoint_requires_session(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    client = app.test_client()

    response = client.get("/api/weather?city=Roma")

    assert response.status_code == 401


def test_weather_endpoint_requires_city_param(tmp_path):
    client = _logged_in_client(tmp_path)

    response = client.get("/api/weather")

    assert response.status_code == 400


def test_weather_endpoint_returns_weather_data(tmp_path):
    client = _logged_in_client(tmp_path)

    with patch(
        "app.utility_routes.get_weather",
        return_value={"city": "Roma", "temp": 27, "description": "cielo sereno"},
    ):
        response = client.get("/api/weather?city=Roma")

    assert response.status_code == 200
    assert response.get_json()["data"]["city"] == "Roma"
