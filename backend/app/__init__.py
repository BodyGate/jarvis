"""Pacchetto applicativo JARVIS backend — app factory Flask (Fase 2: Backend
Core), con REST API, WebSocket e l'hardening di sicurezza richiesto da
ADR-0002 (autenticazione) e ADR-0005 (timeout sessione, rate limiting).
"""
from __future__ import annotations

from datetime import timedelta

from flask import Flask, jsonify, request, session
from flask_cors import CORS

from app.auth import auth_bp
from app.calendar_routes import calendar_bp
from app.chat_routes import chat_bp
from app.config import load_settings
from app.email_routes import email_bp
from app.extensions import limiter, socketio
from app.google_auth_routes import google_auth_bp
from app.utility_routes import utility_bp

# Route pubbliche: le uniche raggiungibili senza sessione valida (ADR-0002).
_PUBLIC_API_PATHS = {"/api/health", "/api/session/login", "/api/session/status"}


def create_app(env_file: str | None = None) -> Flask:
    settings = load_settings(env_file=env_file)

    app = Flask(__name__)
    app.config["JARVIS_SETTINGS"] = settings
    app.config["SECRET_KEY"] = settings.secret_key

    app.config["SESSION_COOKIE_SECURE"] = settings.is_production
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True

    CORS(app, supports_credentials=True)
    limiter.init_app(app)
    socketio.init_app(app, manage_session=True)

    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(utility_bp)
    app.register_blueprint(google_auth_bp)
    app.register_blueprint(email_bp)
    app.register_blueprint(calendar_bp)

    from app import sockets as _sockets  # noqa: F401  (registra gli handler sull'istanza socketio)

    @app.before_request
    def enforce_session():
        path = request.path
        if not path.startswith("/api/"):
            return None
        if path in _PUBLIC_API_PATHS:
            return None
        if not session.get("authenticated"):
            return jsonify({"success": False, "error": "unauthorized"}), 401
        return None

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    return app
