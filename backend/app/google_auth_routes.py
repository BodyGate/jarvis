"""Autenticazione Google OAuth 2.0 (sezione 9.1 del documento di progetto,
tabella "Autenticazione Google"). `/auth/callback` non richiede la sessione
app — vedi ADR-0006 per il perché e per il meccanismo del cookie di stato
che lo protegge comunque da CSRF."""
from __future__ import annotations

import logging
import secrets

from flask import Blueprint, current_app, jsonify, redirect, request

from app.auth import login_required
from app.google_oauth import (
    GoogleOAuthError,
    build_authorization_url,
    exchange_code,
    revoke_token,
)
from app.google_tokens_repo import delete_tokens, get_tokens, save_tokens
from app.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

google_auth_bp = Blueprint("google_auth", __name__, url_prefix="/auth")

_STATE_COOKIE = "oauth_state"
_STATE_COOKIE_MAX_AGE = 600  # 10 minuti, tempo ragionevole per completare il consenso Google


@google_auth_bp.route("/google", methods=["GET"])
@login_required
def start():
    settings = current_app.config["JARVIS_SETTINGS"]
    try:
        url, state = build_authorization_url(settings)
    except GoogleOAuthError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503

    response = redirect(url)
    response.set_cookie(
        _STATE_COOKIE,
        state,
        max_age=_STATE_COOKIE_MAX_AGE,
        httponly=True,
        secure=settings.is_production,
        samesite="Lax",
    )
    return response


@google_auth_bp.route("/callback", methods=["GET"])
def callback():
    settings = current_app.config["JARVIS_SETTINGS"]

    expected_state = request.cookies.get(_STATE_COOKIE)
    received_state = request.args.get("state") or ""
    valid_state = bool(expected_state) and secrets.compare_digest(expected_state, received_state)

    if not valid_state:
        response = jsonify({"success": False, "error": "state OAuth non valido o scaduto"})
        response.status_code = 400
        response.delete_cookie(_STATE_COOKIE)
        return response

    code = request.args.get("code")
    if not code:
        response = jsonify(
            {"success": False, "error": request.args.get("error", "codice di autorizzazione mancante")}
        )
        response.status_code = 400
        response.delete_cookie(_STATE_COOKIE)
        return response

    try:
        token = exchange_code(code, settings)
        db = get_supabase_client(settings)
        save_tokens(db, settings, token)
    except (GoogleOAuthError, ValueError) as exc:
        response = jsonify({"success": False, "error": str(exc)})
        response.status_code = 502
        response.delete_cookie(_STATE_COOKIE)
        return response

    response = jsonify({"success": True, "data": {"message": "Google collegato con successo."}})
    response.delete_cookie(_STATE_COOKIE)
    return response


@google_auth_bp.route("/status", methods=["GET"])
@login_required
def status():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)
    tokens = get_tokens(db, settings)
    return jsonify(
        {
            "success": True,
            "data": {
                "connected": tokens is not None,
                "scopes": tokens["scopes"] if tokens else [],
            },
        }
    )


@google_auth_bp.route("/revoke", methods=["POST"])
@login_required
def revoke():
    settings = current_app.config["JARVIS_SETTINGS"]
    db = get_supabase_client(settings)
    tokens = get_tokens(db, settings)
    if tokens:
        try:
            revoke_token(tokens["access_token"], settings)
        except GoogleOAuthError as exc:
            logger.warning("Revoca lato Google fallita, rimuovo comunque i token locali: %s", exc)
        delete_tokens(db)
    return jsonify({"success": True})
