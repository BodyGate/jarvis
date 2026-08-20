"""Router di intenti (RF-003): classifica ogni messaggio testuale e decide a
quale specialista instradarlo. Usa Groq (Llama 3.3 70B) via `requests`, come
da stack tecnologico (sezione 6.1/6.3 del documento di progetto) — nessun SDK
dedicato, solo l'HTTP client già in uso per le altre API esterne.

L'esecuzione effettiva degli specialisti (meteo, ricerca, email...) è Fase 3:
qui il router produce solo la classificazione, che il chiamante usa per
decidere action_type/action_payload del messaggio.
"""
from __future__ import annotations

import json
import logging

import requests

from app.config import Settings

logger = logging.getLogger(__name__)

# Il documento di progetto (sezione 6.3) prevedeva Llama 3.3 70B su Groq, ma il
# modello è stato rimosso dal catalogo Groq dopo la stesura del documento.
# openai/gpt-oss-20b è l'equivalente attuale più vicino per un router veloce
# (RNF-002: <2s), verificato disponibile su GET /openai/v1/models il 2026-08-20.
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

VALID_TARGETS = {"local", "chatgpt", "claude", "gemini"}
VALID_SPECIALISTS = {
    "weather",
    "search",
    "time",
    "email_read",
    "email_search",
    "calendar_read",
    "calendar_create",
    "other",
}

SYSTEM_PROMPT = """Sei il router di intenti di JARVIS, un assistente personale.
Classifica il messaggio dell'utente in intent, target e specialist, seguendo queste regole:

- target "local": domande semplici gestibili senza un modello pesante. Quando target è
  "local", specialist deve essere uno tra:
  - "weather": meteo
  - "search": ricerca web rapida, notizie, informazioni generiche
  - "time": che ore sono, che giorno è oggi
  - "email_read": leggere le email
  - "email_search": cercare email specifiche
  - "calendar_read": leggere eventi calendario
  - "calendar_create": creare un evento calendario
  - "other": qualsiasi altra richiesta locale che non rientra nei casi sopra
- target "claude": richieste di coding, analisi di documenti, reasoning approfondito
  (specialist non rilevante, usa "other")
- target "chatgpt": richieste di browsing web complesso, creatività, generazione immagini
  (specialist non rilevante, usa "other")
- target "gemini": mai per testo puro (riservato alle immagini, gestite separatamente)

Rispondi SOLO con un oggetto JSON, senza altro testo, in questo formato esatto:
{"intent": "<breve_slug_intento>", "target": "local|chatgpt|claude", "specialist": "<uno_dei_valori_sopra>", "confidence": <0.0-1.0>}
"""


class RouterError(RuntimeError):
    """Sollevato quando la classificazione fallisce (timeout, errore API, risposta non valida)."""


def classify_intent(text: str, settings: Settings) -> dict:
    """Classifica un messaggio testuale. Solleva RouterError se Groq non è
    raggiungibile o non configurato: il chiamante decide il fallback
    (R10 del documento: "fallback a modello generale")."""
    if not settings.groq_api_key:
        raise RouterError("GROQ_API_KEY non configurata")

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    try:
        response = requests.post(
            GROQ_URL,
            json=payload,
            headers=headers,
            timeout=settings.external_service_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RouterError(f"Chiamata a Groq fallita: {exc}") from exc

    try:
        content = response.json()["choices"][0]["message"]["content"]
        classification = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise RouterError(f"Risposta Groq non valida: {exc}") from exc

    target = classification.get("target")
    if target not in VALID_TARGETS or target == "gemini":
        logger.warning("Groq ha restituito un target inatteso: %r", target)
        target = "local"

    specialist = classification.get("specialist")
    if target == "local" and specialist not in VALID_SPECIALISTS:
        logger.warning("Groq ha restituito uno specialist inatteso: %r", specialist)
        specialist = "other"

    return {
        "intent": classification.get("intent", "unknown"),
        "target": target,
        "specialist": specialist if target == "local" else None,
        "confidence": float(classification.get("confidence", 0.0)),
    }


def classify_image_message() -> dict:
    """Un messaggio con immagine allegata va sempre a Gemini (flusso 8.4),
    senza passare dal router Groq."""
    return {"intent": "vision", "target": "gemini", "specialist": None, "confidence": 1.0}
