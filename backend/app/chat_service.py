"""Logica di dominio per conversazioni e messaggi (RF-001, RF-003, RF-004),
condivisa tra l'endpoint REST `/api/chat/message` e l'evento WebSocket
`send_message` per evitare di duplicare la logica di persistenza e routing.

L'esecuzione effettiva degli specialisti locali (meteo, ricerca, email,
calendario — Fase 3 del piano di implementazione) non è ancora collegata:
per target "local" il messaggio viene classificato e salvato correttamente,
ma la risposta lo segnala esplicitamente invece di inventare un risultato.
"""
from __future__ import annotations

from typing import Optional

from supabase import Client

from app.config import Settings
from app.router import RouterError, classify_image_message, classify_intent

DEFAULT_USER_ID = "default"

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


def _build_assistant_reply(classification: dict, context: list[dict], user_text: str) -> tuple[dict, Optional[dict]]:
    """Ritorna (campi_messaggio_assistant, action_payload_o_None)."""
    target = classification["target"]
    intent = classification["intent"]

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

    content = (
        f"Ho classificato la richiesta come «{intent}» (locale). "
        "L'esecuzione degli specialisti locali (meteo, ricerca, email, calendario) "
        "arriva nella Fase 3."
    )
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
            classification = {"intent": "unknown", "target": "local", "confidence": 0.0}

    history_result = (
        db.table("messages")
        .select("role, content")
        .eq("conversation_id", conv_id)
        .order("created_at")
        .execute()
    )

    assistant_fields, action_payload = _build_assistant_reply(
        classification, history_result.data, text
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
