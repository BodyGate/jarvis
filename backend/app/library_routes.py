"""Endpoint della sezione "Libreria": consultare e gestire i fatti che
JARVIS ricorda a lungo termine (RF-013) — prima invisibili all'utente, solo
usati internamente nei prompt."""
from __future__ import annotations

import uuid

from flask import Blueprint, current_app, jsonify

from app.auth import login_required
from app.memory import delete_fact, list_all_facts
from app.supabase_client import get_supabase_client

library_bp = Blueprint("library", __name__, url_prefix="/api/library")


@library_bp.route("/facts", methods=["GET"])
@login_required
def get_facts():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)
    return jsonify({"success": True, "data": {"facts": list_all_facts(db)}})


@library_bp.route("/facts/<fact_id>", methods=["DELETE"])
@login_required
def delete_fact_route(fact_id: str):
    try:
        uuid.UUID(fact_id)
    except ValueError:
        return jsonify({"success": False, "error": f"fact {fact_id!r} non trovato"}), 404

    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)
    if not delete_fact(db, fact_id):
        return jsonify({"success": False, "error": f"fact {fact_id!r} non trovato"}), 404
    return jsonify({"success": True})
