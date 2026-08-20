"""Agente locale companion di JARVIS: va eseguito manualmente sul dispositivo
da controllare (per ora, un PC). Si collega al backend via Socket.IO con un
token per-dispositivo (ottenuto da POST /api/devices, vedi app.device_routes)
e resta in attesa di comandi.

Esegue SOLO azioni da una whitelist fissa (ACTIONS sotto) — mai comandi
arbitrari ricevuti dal server. Questo è deliberato: un errore di
classificazione del router lato backend non deve mai poter tradursi in
un'azione imprevista su questo PC reale.

Configurazione (variabili d'ambiente, es. in un file .env in questa cartella):
  JARVIS_SERVER_URL   es. https://jarvis-backend-wx9x.onrender.com
  JARVIS_DEVICE_TOKEN token ottenuto alla registrazione del dispositivo

Avvio:
  pip install -r requirements.txt
  python agent.py
"""
from __future__ import annotations

import logging
import os
import webbrowser

import socketio
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jarvis-local-agent")

SERVER_URL = os.environ.get("JARVIS_SERVER_URL")
DEVICE_TOKEN = os.environ.get("JARVIS_DEVICE_TOKEN")

if not SERVER_URL or not DEVICE_TOKEN:
    raise SystemExit(
        "Configura JARVIS_SERVER_URL e JARVIS_DEVICE_TOKEN (variabili d'ambiente o file .env) prima di avviare l'agente."
    )


def _action_open_url(params: dict) -> None:
    url = params.get("url")
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"URL non valido: {url!r}")
    webbrowser.open(url)


# Whitelist fissa: il server invia solo {action, params} da questo insieme
# (validato anche lato server, app.device_agent.ALLOWED_ACTIONS) — nessuna
# esecuzione di comandi/script arbitrari, per design.
ACTIONS = {
    "open_url": _action_open_url,
}

sio = socketio.Client(reconnection=True, reconnection_delay=2, reconnection_delay_max=30)


@sio.event
def connect():
    logger.info("Connesso al server, invio autenticazione...")


@sio.event
def connect_error(data):
    logger.error("Connessione rifiutata: %s", data)


@sio.event
def disconnect():
    logger.warning("Disconnesso dal server, riprovo automaticamente...")


@sio.on("agent_command")
def on_agent_command(data):
    data = data or {}
    request_id = data.get("request_id")
    action = data.get("action")
    params = data.get("params") or {}
    logger.info("Comando ricevuto: %s %s", action, params)

    handler = ACTIONS.get(action)
    if handler is None:
        sio.emit("agent_command_result", {"request_id": request_id, "success": False, "error": f"azione sconosciuta: {action}"})
        return

    try:
        handler(params)
        sio.emit("agent_command_result", {"request_id": request_id, "success": True})
    except Exception as exc:  # qualunque errore dell'azione va segnalato al backend, non deve far crashare l'agente
        logger.exception("Comando fallito")
        sio.emit("agent_command_result", {"request_id": request_id, "success": False, "error": str(exc)})


def main() -> None:
    logger.info("Connessione a %s...", SERVER_URL)
    # wait_timeout di default (python-socketio) è 1 secondo: troppo poco per
    # l'autenticazione lato server, che fa due chiamate HTTP sequenziali a
    # Supabase (lookup del token + aggiornamento di last_seen_at) — in
    # locale rientra sotto 1s, ma sulla rete reale verso Render+Supabase no,
    # causando un fallimento di connessione anche quando l'autenticazione
    # lato server va a buon fine (scoperto verificando end-to-end contro la
    # produzione: last_seen_at si aggiornava comunque nonostante l'errore).
    sio.connect(SERVER_URL, auth={"token": DEVICE_TOKEN}, transports=["polling", "websocket"], wait_timeout=15)
    sio.wait()


if __name__ == "__main__":
    main()
