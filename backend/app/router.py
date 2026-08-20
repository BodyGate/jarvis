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
from datetime import datetime
from typing import Optional

import requests

from app.config import Settings

logger = logging.getLogger(__name__)

# Il documento di progetto (sezione 6.3) prevedeva Llama 3.3 70B su Groq, ma il
# modello è stato rimosso dal catalogo Groq dopo la stesura del documento (e,
# verificato di nuovo il 2026-08-20, l'intera API Llama ufficiale di Meta è
# stata dismessa nel frattempo — non è più un'opzione a nessun costo).
# openai/gpt-oss-120b (upgrade da gpt-oss-20b, richiesto dall'utente per
# migliorare la comprensione del linguaggio naturale restando a costo zero)
# è il modello più capace ancora nel piano gratuito Groq, verificato
# disponibile su GET /openai/v1/models il 2026-08-20.
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

VALID_TARGETS = {"local", "chatgpt", "claude", "gemini"}
VALID_SPECIALISTS = {
    "weather",
    "search",
    "time",
    "email_read",
    "email_search",
    "email_send",
    "device_open",
    "calendar_read",
    "calendar_create",
    "conversation_delete",
    "other",
}

def _build_system_prompt() -> str:
    # La data corrente va iniettata ad ogni chiamata: il modello non la conosce
    # (né dal training né altrimenti) e senza di essa non può risolvere
    # riferimenti relativi come "domani" o "venerdì prossimo" (RF-010).
    today = datetime.now().strftime("%A %d/%m/%Y")
    return f"""Sei il router di intenti di JARVIS, un assistente personale.
Oggi è {today}.
Classifica il messaggio dell'utente in intent, target e specialist, seguendo queste regole:

- target "local": domande semplici gestibili senza un modello pesante. Quando target è
  "local", specialist deve essere uno tra:
  - "weather": meteo
  - "search": ricerca web rapida, notizie, informazioni generiche
  - "time": che ore sono, che giorno è oggi
  - "email_read": leggere le email
  - "email_search": cercare email specifiche
  - "email_send": scrivere/inviare una nuova email a qualcuno (non per leggere
    o cercare email esistenti — quelli sono "email_read"/"email_search")
  - "device_open": l'utente chiede di aprire un'app o un sito sul computer
    collegato (es. "apri Spotify sul pc", "apri YouTube")
  - "calendar_read": leggere eventi calendario
  - "calendar_create": creare un evento calendario
  - "conversation_delete": l'utente chiede esplicitamente di cancellare/eliminare
    una o più conversazioni/chat (es. "cancella questa conversazione",
    "elimina questa chat", "elimina tutte le conversazioni", "cancella tutta
    la cronologia") — non per cancellare un singolo messaggio o un'email
  - "other": qualsiasi altra richiesta locale che non rientra nei casi sopra
- target "claude": richieste di coding, analisi di documenti, reasoning approfondito
  (specialist non rilevante, usa "other")
- target "chatgpt": richieste di browsing web complesso, creatività, generazione immagini
  (specialist non rilevante, usa "other")
- target "gemini": mai per testo puro (riservato alle immagini, gestite separatamente)

Quando specialist è "weather", estrai anche il nome della città menzionata
(in italiano, es. "Roma", "Parigi") nel campo "city". Se l'utente non
menziona nessuna città, usa null. Per ogni altro specialist, "city" è null.

Quando specialist è "calendar_read", estrai in "date_range" uno tra
"today", "tomorrow", "week" (default "today" se non specificato). Per ogni
altro specialist, "date_range" è null.

Quando specialist è "calendar_create", estrai:
- "event_title": titolo breve dell'evento
- "event_date": data assoluta in formato YYYY-MM-DD, risolta rispetto a
  oggi (es. "venerdì" o "domani" → la data reale corrispondente)
- "event_time": ora in formato HH:MM (24h), usa "09:00" se non specificata
Per ogni altro specialist questi tre campi sono null.

Quando specialist è "email_send", estrai in "email_to" l'indirizzo email del
destinatario se è esplicitamente presente nel messaggio (es. "mario@esempio.com"),
altrimenti null — non inventare un indirizzo. Per ogni altro specialist,
"email_to" è null.

Quando specialist è "device_open", estrai in "device_url" l'URL da aprire:
se l'utente menziona un URL esplicito usa quello, altrimenti se menziona un
servizio noto usa il suo URL principale (es. Spotify → "https://open.spotify.com",
YouTube → "https://youtube.com", Gmail → "https://mail.google.com", Google
Calendar → "https://calendar.google.com", Google Maps → "https://maps.google.com",
WhatsApp Web → "https://web.whatsapp.com", Netflix → "https://netflix.com").
Se non riesci a determinare un URL con sicurezza, usa null — non inventare.
Per ogni altro specialist, "device_url" è null.

Quando specialist è "conversation_delete", determina "delete_scope":
- "all" se l'utente chiede esplicitamente di eliminare TUTTE le conversazioni
  o l'intera cronologia (es. "elimina tutte le conversazioni", "cancella
  tutto", "elimina tutte", "non serve selezionarle, eliminale tutte")
- "current" se si riferisce a una singola conversazione, quella attiva
  (es. "cancella questa conversazione", "elimina questa chat")
Per ogni altro specialist, "delete_scope" è null.

Rispondi SOLO con un oggetto JSON, senza altro testo, in questo formato esatto:
{{"intent": "<breve_slug_intento>", "target": "local|chatgpt|claude", "specialist": "<uno_dei_valori_sopra>", "city": "<nome_città_o_null>", "date_range": "<today|tomorrow|week|null>", "event_title": "<titolo_o_null>", "event_date": "<YYYY-MM-DD_o_null>", "event_time": "<HH:MM_o_null>", "email_to": "<indirizzo_o_null>", "device_url": "<url_o_null>", "delete_scope": "<all|current|null>", "confidence": <0.0-1.0>}}
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
            {"role": "system", "content": _build_system_prompt()},
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

    def _clean_str(value: object) -> Optional[str]:
        return value.strip() if isinstance(value, str) and value.strip() else None

    city = _clean_str(classification.get("city"))
    date_range = classification.get("date_range")
    if date_range not in {"today", "tomorrow", "week"}:
        date_range = "today"
    event_title = _clean_str(classification.get("event_title"))
    event_date = _clean_str(classification.get("event_date"))
    event_time = _clean_str(classification.get("event_time")) or "09:00"
    email_to = _clean_str(classification.get("email_to"))
    device_url = _clean_str(classification.get("device_url"))
    delete_scope = classification.get("delete_scope")
    if delete_scope not in {"all", "current"}:
        delete_scope = "current"

    specialist = specialist if target == "local" else None

    return {
        "intent": classification.get("intent", "unknown"),
        "target": target,
        "specialist": specialist,
        "city": city if specialist == "weather" else None,
        "date_range": date_range if specialist == "calendar_read" else None,
        "event_title": event_title if specialist == "calendar_create" else None,
        "event_date": event_date if specialist == "calendar_create" else None,
        "event_time": event_time if specialist == "calendar_create" else None,
        "email_to": email_to if specialist == "email_send" else None,
        "device_url": device_url if specialist == "device_open" else None,
        "delete_scope": delete_scope if specialist == "conversation_delete" else None,
        "confidence": float(classification.get("confidence", 0.0)),
    }


def classify_image_message() -> dict:
    """Un messaggio con immagine allegata va sempre a Gemini (flusso 8.4),
    senza passare dal router Groq."""
    return {
        "intent": "vision",
        "target": "gemini",
        "specialist": None,
        "city": None,
        "date_range": None,
        "event_title": None,
        "event_date": None,
        "event_time": None,
        "email_to": None,
        "device_url": None,
        "delete_scope": None,
        "confidence": 1.0,
    }
