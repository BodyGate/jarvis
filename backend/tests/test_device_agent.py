"""Test per il canale verso l'agente locale (app.device_agent)."""
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from app import device_agent
from app.device_agent import (
    DeviceAgentError,
    list_devices,
    register_device,
    revoke_device,
    send_device_command,
)
from tests.fake_supabase import FakeSupabaseClient


@pytest.fixture(autouse=True)
def _reset_device_state():
    """Le mappe di connessione sono stato in-process globale: vanno pulite
    tra un test e l'altro per evitare che si contaminino a vicenda."""
    device_agent._connected_devices.clear()
    device_agent._sid_to_device.clear()
    device_agent._pending.clear()
    yield
    device_agent._connected_devices.clear()
    device_agent._sid_to_device.clear()
    device_agent._pending.clear()


def test_register_device_returns_plaintext_token_once():
    db = FakeSupabaseClient()
    device = register_device(db, "Il mio PC")

    assert device["name"] == "Il mio PC"
    assert "token" in device
    stored = db._store["device_agents"][0]
    assert stored["token_hash"] != device["token"]  # solo l'hash è persistito


def test_list_devices_reports_connected_status():
    db = FakeSupabaseClient()
    device = register_device(db, "PC")
    device_agent._connected_devices[device["id"]] = "sid123"

    devices = list_devices(db)

    assert len(devices) == 1
    assert devices[0]["connected"] is True


def test_list_devices_reports_disconnected_by_default():
    db = FakeSupabaseClient()
    register_device(db, "PC")

    devices = list_devices(db)

    assert devices[0]["connected"] is False


def test_revoke_device_removes_row_and_clears_connection_state():
    db = FakeSupabaseClient()
    device = register_device(db, "PC")
    device_agent._connected_devices[device["id"]] = "sid123"
    device_agent._sid_to_device["sid123"] = device["id"]

    result = revoke_device(db, device["id"])

    assert result is True
    assert not db._store["device_agents"]
    assert device["id"] not in device_agent._connected_devices
    assert "sid123" not in device_agent._sid_to_device


def test_revoke_device_returns_false_for_unknown_id():
    db = FakeSupabaseClient()
    assert revoke_device(db, "does-not-exist") is False


def test_authenticate_matches_correct_token():
    db = FakeSupabaseClient()
    device = register_device(db, "PC")

    device_id = device_agent._authenticate(db, device["token"])

    assert device_id == device["id"]


def test_authenticate_rejects_wrong_token():
    db = FakeSupabaseClient()
    register_device(db, "PC")

    assert device_agent._authenticate(db, "wrong-token") is None


def test_authenticate_connection_returns_false_on_unexpected_error(tmp_path):
    """Regressione: ripulendo lo scaffolding di debug del bug del timeout
    dell'agente, il try/except attorno ad `authenticate_connection` era
    stato rimosso insieme alle variabili diagnostiche — un errore
    imprevisto (es. Supabase temporaneamente irraggiungibile) faceva
    crashare l'handler `connect` di Socket.IO invece di rifiutare la
    connessione in modo pulito."""
    from app import create_app

    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    flask_app = create_app(env_file=str(env_file))

    with flask_app.test_request_context("/"):
        from flask import request

        request.sid = "fake-sid"
        with patch("app.device_agent.get_supabase_client", side_effect=RuntimeError("boom")):
            result = device_agent.authenticate_connection({"token": "whatever"})

    assert result is False


def test_authenticate_rejects_missing_token():
    db = FakeSupabaseClient()
    register_device(db, "PC")

    assert device_agent._authenticate(db, None) is None


def test_send_device_command_rejects_action_outside_whitelist():
    device_agent._connected_devices["dev1"] = "sid1"

    with pytest.raises(DeviceAgentError, match="non consentita"):
        send_device_command("run_shell_command", {"cmd": "rm -rf /"})


def test_send_device_command_fails_when_no_device_connected():
    with pytest.raises(DeviceAgentError, match="Nessun dispositivo"):
        send_device_command("open_url", {"url": "https://example.com"})


def test_send_device_command_returns_result_on_agent_success():
    device_agent._connected_devices["dev1"] = "sid1"

    def fake_emit(event, payload, room=None):
        assert event == "agent_command"
        assert payload["action"] == "open_url"
        device_agent.handle_agent_command_result({"request_id": payload["request_id"], "success": True})

    with patch("app.device_agent.socketio.emit", side_effect=fake_emit):
        result = send_device_command("open_url", {"url": "https://example.com"})

    assert result["success"] is True


def test_send_device_command_raises_on_agent_failure():
    device_agent._connected_devices["dev1"] = "sid1"

    def fake_emit(event, payload, room=None):
        device_agent.handle_agent_command_result(
            {"request_id": payload["request_id"], "success": False, "error": "app non trovata"}
        )

    with patch("app.device_agent.socketio.emit", side_effect=fake_emit):
        with pytest.raises(DeviceAgentError, match="app non trovata"):
            send_device_command("open_url", {"url": "https://example.com"})


def test_send_device_command_raises_on_timeout():
    device_agent._connected_devices["dev1"] = "sid1"

    with patch("app.device_agent.socketio.emit"):  # l'agente non risponde mai
        with patch("app.device_agent.COMMAND_TIMEOUT_SECONDS", 0.05):
            with pytest.raises(DeviceAgentError, match="non ha risposto"):
                send_device_command("open_url", {"url": "https://example.com"})
