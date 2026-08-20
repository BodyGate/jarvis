"""Test per gli endpoint REST della sezione Siti Web (app.site_routes)."""
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import create_app


def _logged_in_client(tmp_path):
    env_file = tmp_path / ".env"
    password_hash = generate_password_hash("correct-horse")
    env_file.write_text(f"SECRET_KEY=test-secret\nAPP_PASSWORD_HASH={password_hash}\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    app.config["TESTING"] = True
    client = app.test_client()
    client.post("/api/session/login", json={"password": "correct-horse"})
    return client


def test_sites_requires_session(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    client = app.test_client()

    assert client.get("/api/sites").status_code == 401


def test_create_site_returns_it(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.site_routes.get_supabase_client", return_value=db):
        response = client.post("/api/sites", json={"url": "https://example.com", "title": "Example"})

    assert response.status_code == 200
    site = response.get_json()["data"]["site"]
    assert site["url"] == "https://example.com"
    assert site["title"] == "Example"


def test_create_site_without_title_is_optional(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.site_routes.get_supabase_client", return_value=db):
        response = client.post("/api/sites", json={"url": "https://example.com"})

    assert response.status_code == 200
    assert response.get_json()["data"]["site"]["title"] is None


def test_create_site_rejects_missing_url(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.site_routes.get_supabase_client", return_value=db):
        response = client.post("/api/sites", json={})

    assert response.status_code == 400


def test_create_site_rejects_invalid_url(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.site_routes.get_supabase_client", return_value=db):
        response = client.post("/api/sites", json={"url": "javascript:alert(1)"})

    assert response.status_code == 400


def test_list_sites_returns_saved_sites(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.site_routes.get_supabase_client", return_value=db):
        client.post("/api/sites", json={"url": "https://example.com"})
        response = client.get("/api/sites")

    assert response.status_code == 200
    sites = response.get_json()["data"]["sites"]
    assert len(sites) == 1
    assert sites[0]["url"] == "https://example.com"


def test_delete_site_removes_it(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.site_routes.get_supabase_client", return_value=db):
        created = client.post("/api/sites", json={"url": "https://example.com"}).get_json()
        site_id = created["data"]["site"]["id"]
        response = client.delete(f"/api/sites/{site_id}")

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_delete_site_returns_404_for_unknown_id(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.site_routes.get_supabase_client", return_value=db):
        response = client.delete("/api/sites/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_delete_site_returns_404_for_non_uuid_id(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.site_routes.get_supabase_client", return_value=db):
        response = client.delete("/api/sites/not-a-uuid")

    assert response.status_code == 404
