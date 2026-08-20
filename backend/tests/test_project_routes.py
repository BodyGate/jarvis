"""Test per gli endpoint REST della sezione Progetti (app.project_routes)."""
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


def test_projects_requires_session(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    client = app.test_client()

    assert client.get("/api/projects").status_code == 401


def test_create_project_returns_it(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.project_routes.get_supabase_client", return_value=db):
        response = client.post("/api/projects", json={"name": "Casa nuova"})

    assert response.status_code == 200
    project = response.get_json()["data"]["project"]
    assert project["name"] == "Casa nuova"


def test_create_project_requires_name(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.project_routes.get_supabase_client", return_value=db):
        response = client.post("/api/projects", json={"name": "  "})

    assert response.status_code == 400


def test_list_projects_includes_conversation_count(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.project_routes.get_supabase_client", return_value=db):
        created = client.post("/api/projects", json={"name": "Lavoro"}).get_json()
        project_id = created["data"]["project"]["id"]

        db.table("conversations").insert({"id": "c1", "user_id": "default", "project_id": project_id}).execute()
        db.table("conversations").insert({"id": "c2", "user_id": "default", "project_id": project_id}).execute()
        db.table("conversations").insert({"id": "c3", "user_id": "default", "project_id": None}).execute()

        response = client.get("/api/projects")

    assert response.status_code == 200
    projects = response.get_json()["data"]["projects"]
    assert len(projects) == 1
    assert projects[0]["conversation_count"] == 2


def test_delete_project_removes_it_without_deleting_conversations(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.project_routes.get_supabase_client", return_value=db):
        created = client.post("/api/projects", json={"name": "Lavoro"}).get_json()
        project_id = created["data"]["project"]["id"]
        db.table("conversations").insert({"id": "c1", "user_id": "default", "project_id": project_id}).execute()

        response = client.delete(f"/api/projects/{project_id}")

    assert response.status_code == 200
    assert not any(p["id"] == project_id for p in db._store["projects"])
    # la conversazione resta, non viene cancellata dalla rimozione del progetto
    assert any(c["id"] == "c1" for c in db._store["conversations"])


def test_delete_project_returns_404_for_unknown_id(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.project_routes.get_supabase_client", return_value=db):
        response = client.delete("/api/projects/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_delete_project_returns_404_for_non_uuid_id(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.project_routes.get_supabase_client", return_value=db):
        response = client.delete("/api/projects/not-a-uuid")

    assert response.status_code == 404
