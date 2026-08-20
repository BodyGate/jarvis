"""Test per gli endpoint REST della sezione Libreria (app.library_routes)."""
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


def test_facts_requires_session(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    client = app.test_client()

    assert client.get("/api/library/facts").status_code == 401


def test_get_facts_returns_saved_facts(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    db.table("user_facts").insert({"user_id": "default", "category": "preference", "fact": "Odia il caffè"}).execute()

    client = _logged_in_client(tmp_path)
    with patch("app.library_routes.get_supabase_client", return_value=db):
        response = client.get("/api/library/facts")

    assert response.status_code == 200
    facts = response.get_json()["data"]["facts"]
    assert len(facts) == 1
    assert facts[0]["fact"] == "Odia il caffè"


def test_delete_fact_removes_it(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    inserted = db.table("user_facts").insert(
        {"user_id": "default", "category": "preference", "fact": "Odia il caffè"}
    ).execute()
    fact_id = inserted.data[0]["id"]

    client = _logged_in_client(tmp_path)
    with patch("app.library_routes.get_supabase_client", return_value=db):
        response = client.delete(f"/api/library/facts/{fact_id}")

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_delete_fact_returns_404_for_unknown_id(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.library_routes.get_supabase_client", return_value=db):
        response = client.delete("/api/library/facts/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_delete_fact_returns_404_for_non_uuid_id(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.library_routes.get_supabase_client", return_value=db):
        response = client.delete("/api/library/facts/not-a-uuid")

    assert response.status_code == 404
