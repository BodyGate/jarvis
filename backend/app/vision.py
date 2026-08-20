"""Analisi immagini (RF-011, flusso 8.4) via Gemini. Il documento di progetto
(sezione 6.3) indicava Gemini 1.5 Flash; il modello non è più disponibile.
Anche `gemini-2.5-flash` (elencato da `GET /v1beta/models`) risulta ritirato
per i nuovi account ("no longer available to new users") — l'errore 404
dell'API stessa indicava come sostituto `gemini-3.6-flash`, verificato
funzionante il 2026-08-20. Chiamata via `requests`, coerente con lo stack
(nessun SDK dedicato), come già fatto per Groq.
"""
from __future__ import annotations

import base64
import binascii

import requests

from app.config import Settings

GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

DEFAULT_PROMPT = (
    "Descrivi il contenuto di questa immagine in italiano, in modo conciso e utile "
    "per un assistente personale (es. se è un documento, riporta i dati principali; "
    "se è una foto generica, descrivine il soggetto)."
)


class VisionError(RuntimeError):
    """Sollevato quando l'analisi dell'immagine fallisce."""


def analyze_image(image_base64: str, settings: Settings, mime_type: str = "image/jpeg") -> str:
    if not settings.gemini_api_key:
        raise VisionError("GEMINI_API_KEY non configurata")

    # Il client potrebbe inviare un data URL (`data:image/png;base64,...`):
    # estraiamo solo la parte base64 e, se presente, il mime type dichiarato.
    payload_data = image_base64
    if payload_data.startswith("data:"):
        header, _, payload_data = payload_data.partition(",")
        if ";" in header:
            mime_type = header[len("data:") :].split(";")[0] or mime_type

    try:
        base64.b64decode(payload_data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise VisionError(f"Immagine non valida (base64 malformato): {exc}") from exc

    body = {
        "contents": [
            {
                "parts": [
                    {"text": DEFAULT_PROMPT},
                    {"inline_data": {"mime_type": mime_type, "data": payload_data}},
                ]
            }
        ],
        # gemini-3.6-flash pensa per default (~18s per un'immagine banale nei
        # nostri test) — troppo per il requisito non negoziabile di 5s max
        # sui servizi esterni. Un budget di reasoning basso ma non-zero (0
        # viene rifiutato con 400 da questo modello) riporta la latenza
        # sotto 1.5s, verificato manualmente il 2026-08-20.
        "generationConfig": {"thinkingConfig": {"thinkingBudget": 128}},
    }

    try:
        response = requests.post(
            GEMINI_URL,
            params={"key": settings.gemini_api_key},
            json=body,
            timeout=settings.external_service_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise VisionError(f"Chiamata a Gemini fallita: {exc}") from exc

    try:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        raise VisionError(f"Risposta Gemini non valida: {exc}") from exc
