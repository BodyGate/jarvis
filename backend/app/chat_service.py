"""Logica di dominio per conversazioni e messaggi (RF-001, RF-003, RF-004),
condivisa tra l'endpoint REST `/api/chat/message` e l'evento WebSocket
`send_message` per evitare di duplicare la logica di persistenza e routing.

Specialisti locali collegati (Fase 3): ricerca web (DuckDuckGo/ddgs), ora
corrente, meteo, lettura/ricerca email e lettura/creazione eventi calendario
(questi ultimi quattro richiedono Google collegato via `/auth/google`).

Nota: gli intervalli "today"/"tomorrow"/"week" per il calendario sono
calcolati sull'ora del server (UTC su Render), non sul fuso orario reale
dell'utente — lo schema del progetto non prevede un fuso orario utente
configurabile.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from supabase import Client

from app.calendar_service import CalendarError, create_event, list_events
from app.config import Settings
from app.constants import DEFAULT_USER_ID
from app.gmail import GmailError, list_messages
from app.google_oauth import GoogleOAuthError
from app.google_tokens_repo import ensure_valid_access_token
from app.local_chat import LocalChatError, generate_reply
from app.router import RouterError, classify_image_message, classify_intent
from app.search import SearchError, web_search
from app.vision import VisionError, analyze_image
from app.weather import WeatherError, get_weather

DELEGATION_URLS = {
    "claude": "https://claude.ai/new",
    "chatgpt": "https://chatgpt.com/",
}


class ChatServiceError(RuntimeError):
    """Errore applicativo esposto come risposta 4xx/5xx dal chiamante."""


def get_or_create_conversation(db: Client, conversation_id: Optional[str], first_message: str) -> dict:
    if conversation_id:
        result = (
            db.table("conversations")
            .select("*")
            .eq("id", conversation_id)
            .eq("user_id", DEFAULT_USER_ID)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise ChatServiceError(f"conversation_id {conversation_id!r} non trovata")
        return result.data[0]

    title = first_message.strip()[:60] or "Nuova conversazione"
    result = (
        db.table("conversations")
        .insert({"user_id": DEFAULT_USER_ID, "title": title})
        .execute()
    )
    return result.data[0]


def _touch_conversation(db: Client, conversation_id: str) -> None:
    from datetime import datetime, timezone

    db.table("conversations").update(
        {"updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", conversation_id).execute()


def _handle_search(user_text: str, settings: Settings) -> str:
    try:
        results = web_search(user_text, settings, max_results=5)
    except SearchError as exc:
        return f"Ricerca non disponibile al momento ({exc})."

    if not results:
        return "Nessun risultato trovato."

    lines = ["Risultati:"]
    for r in results:
        lines.append(f"- {r['title']}: {r['snippet']} ({r['url']})")
    return "\n".join(lines)


def _handle_weather(city: Optional[str], settings: Settings) -> str:
    if not city:
        return "Per quale città vuoi il meteo?"
    try:
        data = get_weather(city, settings)
    except WeatherError as exc:
        return f"Meteo non disponibile al momento ({exc})."
    return f"A {data['city']}: {data['temp']}°C, {data['description']}."


def _handle_email_read(db: Client, settings: Settings) -> str:
    try:
        access_token = ensure_valid_access_token(db, settings)
        emails = list_messages(access_token, settings, max_results=5)
    except GoogleOAuthError as exc:
        return f"Google non è collegato ({exc})."
    except GmailError as exc:
        return f"Lettura email non disponibile al momento ({exc})."

    if not emails:
        return "Nessuna email trovata."
    lines = ["Ultime email:"]
    for e in emails:
        lines.append(f"- {e['from']}: {e['subject']} — {e['snippet']}")
    return "\n".join(lines)


def _handle_email_search(db: Client, user_text: str, settings: Settings) -> str:
    try:
        access_token = ensure_valid_access_token(db, settings)
        emails = list_messages(access_token, settings, query=user_text, max_results=10)
    except GoogleOAuthError as exc:
        return f"Google non è collegato ({exc})."
    except GmailError as exc:
        return f"Ricerca email non disponibile al momento ({exc})."

    if not emails:
        return "Nessuna email trovata per questa ricerca."
    lines = ["Email trovate:"]
    for e in emails:
        lines.append(f"- {e['from']}: {e['subject']} — {e['snippet']}")
    return "\n".join(lines)


def _calendar_range(date_range: str) -> tuple[str, str]:
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if date_range == "tomorrow":
        start = today_start + timedelta(days=1)
        end = start + timedelta(days=1)
    elif date_range == "week":
        start = today_start
        end = start + timedelta(days=7)
    else:
        start = today_start
        end = start + timedelta(days=1)
    return start.isoformat() + "Z", end.isoformat() + "Z"


def _handle_calendar_read(db: Client, date_range: str, settings: Settings) -> str:
    time_min, time_max = _calendar_range(date_range)
    try:
        access_token = ensure_valid_access_token(db, settings)
        events = list_events(access_token, settings, time_min, time_max)
    except GoogleOAuthError as exc:
        return f"Google non è collegato ({exc})."
    except CalendarError as exc:
        return f"Lettura calendario non disponibile al momento ({exc})."

    if not events:
        return "Nessun evento in programma per questo periodo."
    lines = ["Eventi in programma:"]
    for e in events:
        lines.append(f"- {e['start']}: {e['summary']}" + (f" ({e['location']})" if e["location"] else ""))
    return "\n".join(lines)


def _handle_calendar_create(
    db: Client, title: Optional[str], event_date: Optional[str], event_time: str, settings: Settings
) -> str:
    if not title or not event_date:
        return "Non ho capito titolo e data dell'evento da creare — puoi ripetere in modo più esplicito?"

    start_dt = datetime.fromisoformat(f"{event_date}T{event_time}:00")
    end_dt = start_dt + timedelta(hours=1)

    try:
        access_token = ensure_valid_access_token(db, settings)
        create_event(
            access_token,
            settings,
            summary=title,
            start=start_dt.isoformat(),
            end=end_dt.isoformat(),
        )
    except GoogleOAuthError as exc:
        return f"Google non è collegato ({exc})."
    except CalendarError as exc:
        return f"Creazione evento non disponibile al momento ({exc})."

    return f"Aggiunto «{title}» il {start_dt.strftime('%d/%m/%Y')} alle {start_dt.strftime('%H:%M')}."


def _handle_general_chat(user_text: str, context: list[dict], settings: Settings) -> str:
    try:
        return generate_reply(user_text, context, settings)
    except LocalChatError as exc:
        return f"Non sono riuscito a generare una risposta ({exc})."


def _handle_local_specialist(
    db: Client, classification: dict, user_text: str, context: list[dict], settings: Settings
) -> str:
    specialist = classification.get("specialist") or "other"
    if specialist == "search":
        return _handle_search(user_text, settings)
    if specialist == "time":
        now = datetime.now()
        return f"Sono le {now.strftime('%H:%M')} del {now.strftime('%d/%m/%Y')}."
    if specialist == "weather":
        return _handle_weather(classification.get("city"), settings)
    if specialist == "email_read":
        return _handle_email_read(db, settings)
    if specialist == "email_search":
        return _handle_email_search(db, user_text, settings)
    if specialist == "calendar_read":
        return _handle_calendar_read(db, classification.get("date_range") or "today", settings)
    if specialist == "calendar_create":
        return _handle_calendar_create(
            db,
            classification.get("event_title"),
            classification.get("event_date"),
            classification.get("event_time") or "09:00",
            settings,
        )
    # "other": richiesta locale che non rientra in nessuno specialista dedicato
    # (chiacchiere, domande generiche) — risposta reale via Groq, non un segnaposto.
    return _handle_general_chat(user_text, context, settings)


def _build_assistant_reply(
    db: Client,
    classification: dict,
    context: list[dict],
    user_text: str,
    settings: Settings,
    image_base64: Optional[str],
) -> tuple[dict, Optional[dict]]:
    """Ritorna (campi_messaggio_assistant, action_payload_o_None)."""
    target = classification["target"]

    if target == "gemini":
        try:
            content = analyze_image(image_base64, settings)
        except VisionError as exc:
            content = f"Non sono riuscito ad analizzare l'immagine ({exc})."
        message_fields = {"content": content, "action_type": None, "action_payload": None}
        return message_fields, None

    if target in DELEGATION_URLS:
        prompt_lines = ["Contesto conversazione:"]
        for msg in context[-10:]:
            speaker = "Utente" if msg["role"] == "user" else "JARVIS"
            prompt_lines.append(f"{speaker}: {msg['content']}")
        prompt_lines.append(f"Richiesta attuale: {user_text}")
        prompt = "\n".join(prompt_lines)

        action_payload = {
            "type": "copy_and_open",
            "target": target,
            "url": DELEGATION_URLS[target],
            "prompt": prompt,
        }
        content = f"Questa richiesta è per {target.capitalize()} — copia il prompt e aprilo per continuare."
        message_fields = {
            "content": content,
            "action_type": "copy_and_open",
            "action_payload": action_payload,
        }
        return message_fields, action_payload

    content = _handle_local_specialist(db, classification, user_text, context, settings)
    message_fields = {"content": content, "action_type": None, "action_payload": None}
    return message_fields, None


def process_message(
    db: Client,
    settings: Settings,
    *,
    text: str,
    image_base64: Optional[str],
    conversation_id: Optional[str],
) -> dict:
    """Salva il messaggio utente, classifica l'intento, genera e salva la
    risposta dell'assistente. Ritorna {conversation_id, user_message,
    assistant_message, action}.
    """
    if not text and not image_base64:
        raise ChatServiceError("Il messaggio deve contenere testo o un'immagine")

    conversation = get_or_create_conversation(db, conversation_id, text or "Immagine")
    conv_id = conversation["id"]

    has_image = bool(image_base64)
    user_insert = (
        db.table("messages")
        .insert(
            {
                "conversation_id": conv_id,
                "role": "user",
                "content": text or "",
                "has_image": has_image,
            }
        )
        .execute()
    )
    user_message = user_insert.data[0]

    if has_image:
        classification = classify_image_message()
    else:
        try:
            classification = classify_intent(text, settings)
        except RouterError:
            classification = {
                "intent": "unknown",
                "target": "local",
                "specialist": "other",
                "confidence": 0.0,
            }

    history_result = (
        db.table("messages")
        .select("role, content")
        .eq("conversation_id", conv_id)
        .order("created_at")
        .execute()
    )

    assistant_fields, action_payload = _build_assistant_reply(
        db, classification, history_result.data, text, settings, image_base64
    )

    assistant_insert = (
        db.table("messages")
        .insert(
            {
                "conversation_id": conv_id,
                "role": "assistant",
                "content": assistant_fields["content"],
                "intent": classification["intent"],
                "target": classification["target"],
                "source": "groq-router" if not has_image else "gemini-vision",
                "action_type": assistant_fields["action_type"],
                "action_payload": assistant_fields["action_payload"],
            }
        )
        .execute()
    )
    assistant_message = assistant_insert.data[0]

    _touch_conversation(db, conv_id)

    return {
        "conversation_id": conv_id,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "action": action_payload,
    }
