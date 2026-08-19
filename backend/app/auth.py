"""Autenticazione applicativa con password singola (ADR-0002).

Endpoint sotto `/api/session/*`, distinti da `/auth/*` che la Fase 3 userà
per l'OAuth Google (sezione 9.1 del documento di progetto) — evita
collisioni di naming tra i due meccanismi di autenticazione, che restano
concettualmente separati (login all'app vs. autorizzazione a Gmail/Calendar).
"""
from __future__ import annotations

from functools import wraps

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash

from app.extensions import limiter

auth_bp = Blueprint("auth", __name__, url_prefix="/api/session")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify({"success": False, "error": "unauthorized"}), 401
        session.permanent = True
        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per 5 minutes")
def login():
    settings = current_app.config["JARVIS_SETTINGS"]
    if not settings.app_password_hash:
        return (
            jsonify({"success": False, "error": "app_password_not_configured"}),
            503,
        )

    body = request.get_json(silent=True) or {}
    password = body.get("password", "")

    if not password or not check_password_hash(settings.app_password_hash, password):
        return jsonify({"success": False, "error": "invalid_password"}), 401

    session.clear()
    session["authenticated"] = True
    session.permanent = True
    return jsonify({"success": True})


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@auth_bp.route("/status", methods=["GET"])
def status():
    return jsonify({"success": True, "data": {"authenticated": bool(session.get("authenticated"))}})
