"""Entrypoint per lo sviluppo locale (Fase 2, checklist "Flask app funzionante
in locale"). In produzione su Koyeb si userà `wsgi.py` con Gunicorn."""
from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    socketio.run(
        app,
        host="127.0.0.1",
        port=5000,
        debug=not app.config["JARVIS_SETTINGS"].is_production,
        use_reloader=False,
    )
