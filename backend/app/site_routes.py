"""Endpoint della sezione "Siti Web": link salvati dall'utente."""
from __future__ import annotations

import uuid

from flask import Blueprint, current_app, jsonify, request

from app.auth import login_required
from app.constants import DEFAULT_USER_ID
from app.supabase_client import get_supabase_client

site_bp = Blueprint("sites", __name__, url_prefix="/api/sites")


@site_bp.route("", methods=["GET"])
@login_required
def list_sites():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    sites = (
        db.table("saved_sites")
        .select("id, url, title, created_at")
        .eq("user_id", DEFAULT_USER_ID)
        .order("created_at", desc=True)
        .execute()
        .data
    )
    return jsonify({"success": True, "data": {"sites": sites}})


@site_bp.route("", methods=["POST"])
@login_required
def create_site():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    title = (body.get("title") or "").strip() or None
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"success": False, "error": "url mancante o non valido"}), 400

    result = (
        db.table("saved_sites")
        .insert({"user_id": DEFAULT_USER_ID, "url": url, "title": title})
        .execute()
    )
    return jsonify({"success": True, "data": {"site": result.data[0]}})


@site_bp.route("/<site_id>", methods=["DELETE"])
@login_required
def delete_site(site_id: str):
    try:
        uuid.UUID(site_id)
    except ValueError:
        return jsonify({"success": False, "error": f"site {site_id!r} non trovato"}), 404

    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)

    result = (
        db.table("saved_sites")
        .delete()
        .eq("id", site_id)
        .eq("user_id", DEFAULT_USER_ID)
        .execute()
    )
    if not result.data:
        return jsonify({"success": False, "error": f"site {site_id!r} non trovato"}), 404
    return jsonify({"success": True})
