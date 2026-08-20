"""Endpoint della sezione "Progetti": raggruppare conversazioni correlate."""
from __future__ import annotations

import uuid

from flask import Blueprint, current_app, jsonify, request

from app.auth import login_required
from app.constants import DEFAULT_USER_ID
from app.supabase_client import get_supabase_client

project_bp = Blueprint("projects", __name__, url_prefix="/api/projects")


@project_bp.route("", methods=["GET"])
@login_required
def list_projects():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    projects = (
        db.table("projects")
        .select("id, name, created_at")
        .eq("user_id", DEFAULT_USER_ID)
        .order("created_at")
        .execute()
        .data
    )

    # Conteggio conversazioni per progetto: una sola query aggregata invece
    # di una per progetto (stesso pattern già usato per message_count in
    # app.chat_routes).
    conv_result = (
        db.table("conversations")
        .select("project_id")
        .eq("user_id", DEFAULT_USER_ID)
        .execute()
    )
    counts: dict[str, int] = {}
    for c in conv_result.data:
        pid = c.get("project_id")
        if pid:
            counts[pid] = counts.get(pid, 0) + 1

    for p in projects:
        p["conversation_count"] = counts.get(p["id"], 0)

    return jsonify({"success": True, "data": {"projects": projects}})


@project_bp.route("", methods=["POST"])
@login_required
def create_project():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "name mancante"}), 400

    result = db.table("projects").insert({"user_id": DEFAULT_USER_ID, "name": name}).execute()
    return jsonify({"success": True, "data": {"project": result.data[0]}})


@project_bp.route("/<project_id>", methods=["DELETE"])
@login_required
def delete_project(project_id: str):
    try:
        uuid.UUID(project_id)
    except ValueError:
        return jsonify({"success": False, "error": f"project {project_id!r} non trovato"}), 404

    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    # Le conversazioni nel progetto non vengono cancellate, solo scollegate
    # (project_id ON DELETE SET NULL, sezione 7.1 schema).
    result = (
        db.table("projects")
        .delete()
        .eq("id", project_id)
        .eq("user_id", DEFAULT_USER_ID)
        .execute()
    )
    if not result.data:
        return jsonify({"success": False, "error": f"project {project_id!r} non trovato"}), 404
    return jsonify({"success": True})
