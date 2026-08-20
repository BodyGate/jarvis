"""Endpoint calendario (sezione 9.1, tabella "Calendario"; RF-009, RF-010)."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.auth import login_required
from app.calendar_service import CalendarError, create_event, delete_event, list_events
from app.google_oauth import GoogleOAuthError
from app.google_tokens_repo import ensure_valid_access_token
from app.supabase_client import get_supabase_client

calendar_bp = Blueprint("calendar", __name__, url_prefix="/api/calendar")


def _access_token(settings):
    db = get_supabase_client(settings)
    return ensure_valid_access_token(db, settings)


@calendar_bp.route("/events", methods=["GET"])
@login_required
def events():
    settings = current_app.config["JARVIS_SETTINGS"]
    time_min = request.args.get("time_min")
    time_max = request.args.get("time_max")
    if not time_min or not time_max:
        return jsonify({"success": False, "error": "time_min e time_max sono obbligatori"}), 400

    try:
        access_token = _access_token(settings)
        result = list_events(access_token, settings, time_min, time_max)
    except GoogleOAuthError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except CalendarError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502

    return jsonify({"success": True, "data": {"events": result}})


@calendar_bp.route("/event", methods=["POST"])
@login_required
def create():
    settings = current_app.config["JARVIS_SETTINGS"]
    body = request.get_json(silent=True) or {}
    summary = body.get("summary")
    start = body.get("start")
    end = body.get("end")
    if not summary or not start or not end:
        return jsonify({"success": False, "error": "summary, start e end sono obbligatori"}), 400

    try:
        access_token = _access_token(settings)
        event_id = create_event(
            access_token,
            settings,
            summary=summary,
            start=start,
            end=end,
            location=body.get("location", ""),
            description=body.get("description", ""),
        )
    except GoogleOAuthError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except CalendarError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502

    return jsonify({"success": True, "data": {"event_id": event_id}})


@calendar_bp.route("/event/<event_id>", methods=["DELETE"])
@login_required
def delete(event_id: str):
    settings = current_app.config["JARVIS_SETTINGS"]

    try:
        access_token = _access_token(settings)
        delete_event(access_token, event_id, settings)
    except GoogleOAuthError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except CalendarError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502

    return jsonify({"success": True})
