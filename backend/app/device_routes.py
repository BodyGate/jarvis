"""Endpoint per registrare e gestire i dispositivi locali collegabili a
JARVIS (agente companion — vedi app.device_agent e local_agent/agent.py)."""
from __future__ import annotations

import uuid

from flask import Blueprint, current_app, jsonify, request

from app.auth import login_required
from app.device_agent import list_devices, register_device, revoke_device
from app.supabase_client import get_supabase_client

device_bp = Blueprint("devices", __name__, url_prefix="/api/devices")


@device_bp.route("", methods=["GET"])
@login_required
def get_devices():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)
    return jsonify({"success": True, "data": {"devices": list_devices(db)}})


@device_bp.route("", methods=["POST"])
@login_required
def create_device():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip() or "PC"
    device = register_device(db, name)
    return jsonify({"success": True, "data": {"device": device}})


@device_bp.route("/<device_id>", methods=["DELETE"])
@login_required
def delete_device(device_id: str):
    try:
        uuid.UUID(device_id)
    except ValueError:
        return jsonify({"success": False, "error": f"device {device_id!r} non trovato"}), 404

    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)
    if not revoke_device(db, device_id):
        return jsonify({"success": False, "error": f"device {device_id!r} non trovato"}), 404
    return jsonify({"success": True})


# TODO(temporaneo): diagnostica per il bug "connessione agente rifiutata solo
# in produzione" — rimuovere questo endpoint una volta risolto.
@device_bp.route("/_debug_last_error", methods=["GET"])
@login_required
def debug_last_error():
    from app import device_agent

    return jsonify({"success": True, "data": {"error": device_agent._last_connect_error}})
