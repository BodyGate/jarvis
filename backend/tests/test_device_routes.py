"""Test per gli endpoint REST di gestione dispositivi (app.device_routes)."""
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import create_app
from app import device_agent


def _logged_in_client(tmp_path):
    env_file = tmp_path / ".env"
    password_hash = generate_password_hash("correct-horse")
    env_file.write_text(f"SECRET_KEY=test-secret\nAPP_PASSWORD_HASH={password_hash}\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    app.config["TESTING"] = True
    client = app.test_client()
    client.post("/api/session/login", json={"password": "correct-horse"})
    return client


def test_devices_requires_session(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    client = app.test_client()

    assert client.get("/api/devices").status_code == 401


def test_create_device_returns_token_once(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.device_routes.get_supabase_client", return_value=db):
        response = client.post("/api/devices", json={"name": "Il mio PC"})

    assert response.status_code == 200
    body = response.get_json()["data"]["device"]
    assert body["name"] == "Il mio PC"
    assert "token" in body


def test_list_devices_returns_registered_devices(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.device_routes.get_supabase_client", return_value=db):
        client.post("/api/devices", json={"name": "PC"})
        response = client.get("/api/devices")

    assert response.status_code == 200
    devices = response.get_json()["data"]["devices"]
    assert len(devices) == 1
    assert devices[0]["name"] == "PC"
    assert devices[0]["connected"] is False


def test_delete_device_removes_it(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.device_routes.get_supabase_client", return_value=db):
        created = client.post("/api/devices", json={"name": "PC"}).get_json()
        device_id = created["data"]["device"]["id"]
        response = client.delete(f"/api/devices/{device_id}")

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_delete_device_returns_404_for_unknown_id(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.device_routes.get_supabase_client", return_value=db):
        response = client.delete("/api/devices/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_delete_device_returns_404_for_non_uuid_id(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.device_routes.get_supabase_client", return_value=db):
        response = client.delete("/api/devices/not-a-uuid")

    assert response.status_code == 404
