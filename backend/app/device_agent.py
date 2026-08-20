"""Canale verso l'agente locale companion (PC): un processo Python separato
dal browser, eseguito manualmente sul dispositivo da controllare (vedi
`local_agent/agent.py`), che si collega via Socket.IO e resta in attesa di
comandi. Richiesta esplicita dell'utente ("voglio che si colleghi al
dispositivo dove è installato per poterlo gestire"), scelta deliberatamente
a whitelist fissa: il server non invia mai un comando arbitrario, solo
{action, params} da un set noto (`ALLOWED_ACTIONS`) — un errore di
classificazione del router qui avrebbe un impatto reale su un PC vero, non
su un test isolato.

L'agente non ha una sessione browser (niente cookie): l'handler `connect`
di Socket.IO lo autentica con un token per-dispositivo passato come `auth`
alla connessione, verificato contro l'hash salvato (stesso meccanismo di
APP_PASSWORD_HASH).
"""
from __future__ import annotations

import logging
import secrets
import uuid as uuid_module
from datetime import datetime, timezone
from typing import Optional

from flask import current_app, request
from gevent import Timeout as GeventTimeout
from gevent.event import AsyncResult
from supabase import Client
from werkzeug.security import check_password_hash, generate_password_hash

from app.constants import DEFAULT_USER_ID
from app.extensions import socketio
from app.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = {"open_url"}
COMMAND_TIMEOUT_SECONDS = 10

# Stato in-process: il servizio gira con un solo worker gunicorn (`-w 1`,
# già richiesto da Flask-SocketIO con gevent), quindi non serve gestire un
# fan-out multi-processo per queste mappe.
_connected_devices: dict[str, str] = {}  # device_id -> socketio sid
_sid_to_device: dict[str, str] = {}  # sid -> device_id
_pending: dict[str, AsyncResult] = {}  # request_id -> AsyncResult


class DeviceAgentError(RuntimeError):
    """Sollevato quando un comando non può essere inoltrato o eseguito sull'agente."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_device(db: Client, name: str) -> dict:
    """Crea un nuovo dispositivo e ritorna {id, name, token}. Il token in
    chiaro è visibile solo in questa risposta: da qui in poi solo il suo
    hash resta su Supabase, esattamente come per APP_PASSWORD_HASH."""
    token = secrets.token_urlsafe(32)
    row = {
        "user_id": DEFAULT_USER_ID,
        "name": name,
        "token_hash": generate_password_hash(token),
    }
    result = db.table("device_agents").insert(row).execute()
    device = result.data[0]
    return {"id": device["id"], "name": device["name"], "token": token}


def list_devices(db: Client) -> list[dict]:
    result = (
        db.table("device_agents")
        .select("id, name, last_seen_at, created_at")
        .eq("user_id", DEFAULT_USER_ID)
        .order("created_at")
        .execute()
    )
    devices = result.data
    for d in devices:
        d["connected"] = d["id"] in _connected_devices
    return devices


def revoke_device(db: Client, device_id: str) -> bool:
    result = (
        db.table("device_agents")
        .delete()
        .eq("id", device_id)
        .eq("user_id", DEFAULT_USER_ID)
        .execute()
    )
    revoked = bool(result.data)
    if revoked:
        sid = _connected_devices.pop(device_id, None)
        if sid is not None:
            _sid_to_device.pop(sid, None)
    return revoked


def _authenticate(db: Client, token: Optional[str]) -> Optional[str]:
    """Numero di dispositivi per utente atteso piccolo (uso personale): un
    confronto lineare degli hash è sufficiente."""
    if not token:
        return None
    result = (
        db.table("device_agents")
        .select("id, token_hash")
        .eq("user_id", DEFAULT_USER_ID)
        .execute()
    )
    for row in result.data:
        if check_password_hash(row["token_hash"], token):
            return row["id"]
    return None


_last_connect_error: Optional[str] = None  # diagnostica temporanea, vedi TODO in fondo al file


def authenticate_connection(auth: Optional[dict]) -> bool:
    """Chiamata dall'handler `connect` di Socket.IO per i client privi di
    sessione browser valida — cioè un agente locale."""
    global _last_connect_error
    try:
        token = (auth or {}).get("token") if isinstance(auth, dict) else None
        settings = current_app.config["JARVIS_SETTINGS"]
        db = get_supabase_client(settings)
        device_id = _authenticate(db, token)
        if device_id is None:
            return False

        _connected_devices[device_id] = request.sid
        _sid_to_device[request.sid] = device_id
        db.table("device_agents").update({"last_seen_at": _now_iso()}).eq("id", device_id).execute()
        logger.info("Device agent collegato: %s", device_id)
        return True
    except Exception:
        import traceback

        _last_connect_error = traceback.format_exc()
        logger.exception("authenticate_connection ha sollevato un'eccezione")
        return False


def handle_disconnect() -> None:
    device_id = _sid_to_device.pop(request.sid, None)
    if device_id is not None:
        _connected_devices.pop(device_id, None)
        logger.info("Device agent disconnesso: %s", device_id)


def get_connected_device_id() -> Optional[str]:
    """Unico dispositivo collegato al momento, o None — questa prima
    versione assume un solo PC collegato per utente."""
    if not _connected_devices:
        return None
    return next(iter(_connected_devices))


def send_device_command(action: str, params: dict) -> dict:
    if action not in ALLOWED_ACTIONS:
        raise DeviceAgentError(f"Azione non consentita: {action}")

    device_id = get_connected_device_id()
    if device_id is None:
        raise DeviceAgentError("Nessun dispositivo collegato al momento")

    sid = _connected_devices[device_id]
    request_id = uuid_module.uuid4().hex
    async_result = AsyncResult()
    _pending[request_id] = async_result

    try:
        socketio.emit(
            "agent_command",
            {"request_id": request_id, "action": action, "params": params},
            room=sid,
        )
        try:
            result = async_result.get(timeout=COMMAND_TIMEOUT_SECONDS)
        except GeventTimeout as exc:
            # gevent.Timeout eredita da BaseException, non da Exception: un
            # `except Exception` qui non la intercetterebbe e lascerebbe
            # propagare l'eccezione grezza invece del messaggio applicativo.
            raise DeviceAgentError("Il dispositivo non ha risposto in tempo") from exc
    finally:
        _pending.pop(request_id, None)

    if not result.get("success"):
        raise DeviceAgentError(result.get("error") or "Comando fallito sul dispositivo")
    return result


@socketio.on("agent_command_result")
def handle_agent_command_result(data):
    data = data or {}
    request_id = data.get("request_id")
    async_result = _pending.get(request_id)
    if async_result is not None and not async_result.ready():
        async_result.set(data)
