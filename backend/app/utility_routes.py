"""Endpoint di utilità (sezione 9.1 del documento di progetto, tabella "Utility")."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.auth import login_required
from app.weather import WeatherError, get_weather

utility_bp = Blueprint("utility", __name__, url_prefix="/api")


@utility_bp.route("/weather", methods=["GET"])
@login_required
def weather():
    settings = current_app.config["JARVIS_SETTINGS"]
    city = request.args.get("city")
    if not city:
        return jsonify({"success": False, "error": "city mancante"}), 400

    try:
        data = get_weather(city, settings)
    except WeatherError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502

    return jsonify({"success": True, "data": data})
