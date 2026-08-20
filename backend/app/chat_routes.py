"""Endpoint REST della chat (sezione 9.1 del documento di progetto)."""
from __future__ import annotations

import uuid

from flask import Blueprint, current_app, jsonify, request

from app.auth import login_required
from app.chat_service import DEFAULT_USER_ID, ChatServiceError, process_message
from app.extensions import limiter
from app.supabase_client import get_supabase_client

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@chat_bp.route("/message", methods=["POST"])
@login_required
@limiter.limit("15 per minute")
def send_message():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    image = body.get("image")
    conversation_id = body.get("conversation_id")

    try:
        result = process_message(
            db,
            settings,
            text=text,
            image_base64=image,
            conversation_id=conversation_id,
        )
    except ChatServiceError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify(
        {
            "success": True,
            "data": {
                "message": result["assistant_message"],
                "action": result["action"],
                "conversation_id": result["conversation_id"],
            },
        }
    )


@chat_bp.route("/history", methods=["GET"])
@login_required
def history():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    conversation_id = request.args.get("conversation_id")
    if not conversation_id:
        return jsonify({"success": False, "error": "conversation_id mancante"}), 400

    result = (
        db.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
    )
    return jsonify({"success": True, "data": {"messages": result.data}})


@chat_bp.route("/clear", methods=["POST"])
@login_required
def clear():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    body = request.get_json(silent=True) or {}
    conversation_id = body.get("conversation_id")
    if not conversation_id:
        return jsonify({"success": False, "error": "conversation_id mancante"}), 400

    db.table("messages").delete().eq("conversation_id", conversation_id).execute()
    return jsonify({"success": True})


@chat_bp.route("/conversations", methods=["GET"])
@login_required
def conversations():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    result = (
        db.table("conversations")
        .select("*")
        .eq("user_id", DEFAULT_USER_ID)
        .order("updated_at", desc=True)
        .execute()
    )
    convs = result.data

    # Conteggio messaggi e ultimo "brain" per conversazione (per la UI 3D,
    # sezione "Constellation"/pannello dettaglio): una sola query aggregata
    # invece di una per conversazione (N+1), che scalerebbe male anche con
    # poche decine di conversazioni.
    conv_ids = [c["id"] for c in convs]
    counts: dict[str, int] = {}
    last_target: dict[str, str] = {}
    if conv_ids:
        msg_result = (
            db.table("messages")
            .select("conversation_id, role, target, created_at")
            .in_("conversation_id", conv_ids)
            .order("created_at")
            .execute()
        )
        for m in msg_result.data:
            cid = m["conversation_id"]
            counts[cid] = counts.get(cid, 0) + 1
            if m["role"] == "assistant" and m.get("target"):
                last_target[cid] = m["target"]  # ordinati per data: l'ultimo sovrascrive

    for c in convs:
        c["message_count"] = counts.get(c["id"], 0)
        c["last_target"] = last_target.get(c["id"])

    return jsonify({"success": True, "data": {"conversations": convs}})


@chat_bp.route("/conversations/<conversation_id>", methods=["DELETE"])
@login_required
def delete_conversation(conversation_id: str):
    """Elimina una conversazione e, in cascata (schema Fase 1), i suoi
    messaggi. Endpoint diretto per il frontend, oltre alla cancellazione
    via chat (specialist "conversation_delete")."""
    try:
        uuid.UUID(conversation_id)
    except ValueError:
        return jsonify({"success": False, "error": f"conversation_id {conversation_id!r} non trovata"}), 404

    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    result = (
        db.table("conversations")
        .delete()
        .eq("id", conversation_id)
        .eq("user_id", DEFAULT_USER_ID)
        .execute()
    )
    if not result.data:
        return jsonify({"success": False, "error": f"conversation_id {conversation_id!r} non trovata"}), 404

    return jsonify({"success": True})


@chat_bp.route("/conversations/<conversation_id>/project", methods=["PUT"])
@login_required
def assign_conversation_project(conversation_id: str):
    """Assegna (o rimuove, con project_id null) una conversazione a un
    progetto — sezione "Progetti"."""
    try:
        uuid.UUID(conversation_id)
    except ValueError:
        return jsonify({"success": False, "error": f"conversation_id {conversation_id!r} non trovata"}), 404

    body = request.get_json(silent=True) or {}
    project_id = body.get("project_id")
    if project_id is not None:
        try:
            uuid.UUID(project_id)
        except ValueError:
            return jsonify({"success": False, "error": f"project_id {project_id!r} non valido"}), 400

    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    result = (
        db.table("conversations")
        .update({"project_id": project_id})
        .eq("id", conversation_id)
        .eq("user_id", DEFAULT_USER_ID)
        .execute()
    )
    if not result.data:
        return jsonify({"success": False, "error": f"conversation_id {conversation_id!r} non trovata"}), 404

    return jsonify({"success": True, "data": {"conversation": result.data[0]}})
