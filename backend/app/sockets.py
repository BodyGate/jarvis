"""Eventi WebSocket (sezione 9.2 del documento di progetto), verificati con
sessione Flask valida (ADR-0002: "il WebSocket verifica la sessione alla
connessione")."""
from __future__ import annotations

from flask import current_app, request, session
from flask_socketio import emit, join_room

from app.chat_service import ChatServiceError, process_message
from app.device_agent import authenticate_connection, handle_disconnect as _handle_device_disconnect
from app.extensions import socketio
from app.supabase_client import get_supabase_client


def _require_session() -> bool:
    return bool(session.get("authenticated"))


@socketio.on("connect")
def handle_connect(auth=None):
    if _require_session():
        return True
    # Nessuna sessione browser: prova ad autenticare come agente locale
    # (vedi app.device_agent) prima di rifiutare la connessione.
    return authenticate_connection(auth)


@socketio.on("disconnect")
def handle_disconnect():
    # No-op per i client browser (non tracciati qui): rilevante solo per
    # ripulire lo stato di un eventuale agente locale disconnesso.
    _handle_device_disconnect()


@socketio.on("join_conversation")
def handle_join_conversation(data):
    if not _require_session():
        return
    conversation_id = (data or {}).get("conversation_id")
    if conversation_id:
        join_room(conversation_id)


@socketio.on("send_message")
def handle_send_message(data):
    if not _require_session():
        return

    data = data or {}
    text = (data.get("text") or "").strip()
    image = data.get("image")
    conversation_id = data.get("conversation_id")

    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    emit("typing", {"status": "start"}, room=request.sid)
    try:
        result = process_message(
            db,
            settings,
            text=text,
            image_base64=image,
            conversation_id=conversation_id,
        )
    except ChatServiceError as exc:
        emit("typing", {"status": "stop"}, room=request.sid)
        emit("error", {"error": str(exc)}, room=request.sid)
        return

    emit("typing", {"status": "stop"}, room=request.sid)
    emit(
        "message",
        {**result["assistant_message"], "action": result["action"]},
        room=request.sid,
    )


@socketio.on("action_triggered")
def handle_action_triggered(data):
    if not _require_session():
        return
    # L'esecuzione delle azioni (es. invio email) richiede le integrazioni
    # della Fase 3: per ora l'evento è riconosciuto ma non eseguito.
    emit(
        "action_result",
        {"success": False, "error": "not_implemented", "data": data},
        room=request.sid,
    )
