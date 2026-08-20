"""Test per gli endpoint REST della chat (sezione 9.1)."""
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


def test_conversations_requires_session(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    client = app.test_client()

    assert client.get("/api/chat/conversations").status_code == 401


def test_conversations_includes_message_count_and_last_brain(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    db.table("conversations").insert({"id": "c1", "user_id": "default", "title": "Prima"}).execute()
    db.table("conversations").insert({"id": "c2", "user_id": "default", "title": "Seconda"}).execute()
    db.table("messages").insert({"conversation_id": "c1", "role": "user", "content": "ciao"}).execute()
    db.table("messages").insert({"conversation_id": "c1", "role": "assistant", "content": "ciao a te", "target": "local"}).execute()
    db.table("messages").insert({"conversation_id": "c1", "role": "user", "content": "altro"}).execute()
    db.table("messages").insert({"conversation_id": "c1", "role": "assistant", "content": "risposta", "target": "claude"}).execute()

    client = _logged_in_client(tmp_path)
    with patch("app.chat_routes.get_supabase_client", return_value=db):
        response = client.get("/api/chat/conversations")

    assert response.status_code == 200
    convs = {c["id"]: c for c in response.get_json()["data"]["conversations"]}
    assert convs["c1"]["message_count"] == 4
    assert convs["c1"]["last_target"] == "claude"  # l'ultimo messaggio assistant, non il primo
    assert convs["c2"]["message_count"] == 0
    assert convs["c2"]["last_target"] is None


def test_delete_conversation_requires_session(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    app = create_app(env_file=str(env_file))
    client = app.test_client()

    assert client.delete("/api/chat/conversations/c1").status_code == 401


def test_delete_conversation_removes_it_and_cascades_messages(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    conv_id = "11111111-1111-1111-1111-111111111111"
    db = FakeSupabaseClient()
    db.table("conversations").insert({"id": conv_id, "user_id": "default", "title": "Prima"}).execute()
    db.table("messages").insert({"conversation_id": conv_id, "role": "user", "content": "ciao"}).execute()

    client = _logged_in_client(tmp_path)
    with patch("app.chat_routes.get_supabase_client", return_value=db):
        response = client.delete(f"/api/chat/conversations/{conv_id}")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert not any(c["id"] == conv_id for c in db._store["conversations"])


def test_delete_conversation_returns_404_for_unknown_id(tmp_path):
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.chat_routes.get_supabase_client", return_value=db):
        response = client.delete("/api/chat/conversations/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_delete_conversation_returns_404_for_non_uuid_id(tmp_path):
    """Un id non-UUID farebbe fallire la query Postgres reale con un 500
    (`invalid input syntax for type uuid`) invece del 404 atteso — va
    intercettato prima di interrogare il DB."""
    from tests.fake_supabase import FakeSupabaseClient

    db = FakeSupabaseClient()
    client = _logged_in_client(tmp_path)
    with patch("app.chat_routes.get_supabase_client", return_value=db):
        response = client.delete("/api/chat/conversations/does-not-exist")

    assert response.status_code == 404
