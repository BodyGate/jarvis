"""Endpoint email (sezione 9.1, tabella "Email"; RF-005→RF-008)."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.auth import login_required
from app.gmail import GmailError, create_draft, get_message, list_messages, send_draft
from app.google_oauth import GoogleOAuthError
from app.google_tokens_repo import ensure_valid_access_token
from app.supabase_client import get_supabase_client

email_bp = Blueprint("email", __name__, url_prefix="/api/email")


def _access_token(settings):
    db = get_supabase_client(settings)
    return ensure_valid_access_token(db, settings)


@email_bp.route("/list", methods=["GET"])
@login_required
def list_emails():
    settings = current_app.config["JARVIS_SETTINGS"]
    max_results = request.args.get("max_results", default=10, type=int)
    query = request.args.get("query", default="")

    try:
        access_token = _access_token(settings)
        emails = list_messages(access_token, settings, query=query, max_results=max_results)
    except GoogleOAuthError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except GmailError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502

    return jsonify({"success": True, "data": {"emails": emails}})


@email_bp.route("/search", methods=["GET"])
@login_required
def search_emails():
    settings = current_app.config["JARVIS_SETTINGS"]
    query = request.args.get("q", default="")
    if not query:
        return jsonify({"success": False, "error": "q mancante"}), 400

    try:
        access_token = _access_token(settings)
        emails = list_messages(access_token, settings, query=query, max_results=20)
    except GoogleOAuthError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except GmailError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502

    return jsonify({"success": True, "data": {"emails": emails}})


@email_bp.route("/<message_id>", methods=["GET"])
@login_required
def get_email(message_id: str):
    settings = current_app.config["JARVIS_SETTINGS"]

    try:
        access_token = _access_token(settings)
        email = get_message(access_token, message_id, settings)
    except GoogleOAuthError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except GmailError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502

    return jsonify({"success": True, "data": {"email": email}})


@email_bp.route("/draft", methods=["POST"])
@login_required
def draft_email():
    settings = current_app.config["JARVIS_SETTINGS"]
    body = request.get_json(silent=True) or {}
    to = body.get("to")
    subject = body.get("subject")
    text = body.get("body")
    reply_to = body.get("reply_to")

    if not to or not subject or not text:
        return jsonify({"success": False, "error": "to, subject e body sono obbligatori"}), 400

    try:
        access_token = _access_token(settings)
        draft_id = create_draft(
            access_token, settings, to=to, subject=subject, body=text, reply_to_message_id=reply_to
        )
    except GoogleOAuthError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except GmailError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502

    return jsonify({"success": True, "data": {"draft_id": draft_id}})


@email_bp.route("/send", methods=["POST"])
@login_required
def send_email():
    settings = current_app.config["JARVIS_SETTINGS"]
    body = request.get_json(silent=True) or {}
    draft_id = body.get("draft_id")
    if not draft_id:
        return jsonify({"success": False, "error": "draft_id mancante"}), 400

    try:
        access_token = _access_token(settings)
        message_id = send_draft(access_token, draft_id, settings)
    except GoogleOAuthError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except GmailError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502

    return jsonify({"success": True, "data": {"message_id": message_id}})
