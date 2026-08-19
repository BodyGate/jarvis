"""Endpoint REST della chat (sezione 9.1 del documento di progetto)."""
from __future__ import annotations

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
    return jsonify({"success": True, "data": {"conversations": result.data}})
