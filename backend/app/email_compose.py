"""Composizione del testo di un'email (specialist "email_send", RF-007) via
Groq: il router si limita a riconoscere l'intento e il destinatario, la
scrittura vera e propria di oggetto e corpo è un compito distinto (stesso
principio già seguito da `app.local_chat` per lo specialist "other")."""
from __future__ import annotations

import json
import logging

import requests

from app.config import Settings

logger = logging.getLogger(__name__)

GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """Sei JARVIS, l'assistente personale dell'utente. Ti ha chiesto di scrivere
un'email. Scrivi un oggetto breve e un corpo email completo e ben scritto in italiano,
nel tono appropriato al contenuto richiesto. Non inventare dettagli (nomi, date, importi)
che l'utente non ha fornito. Non includere un indirizzo o un destinatario nel corpo,
solo il testo del messaggio.
Rispondi SOLO con un oggetto JSON in questo formato esatto: {"subject": "...", "body": "..."}"""


class EmailComposeError(RuntimeError):
    """Sollevato quando la composizione dell'email fallisce."""


# Il modello (gpt-oss-20b, con guardrail di sicurezza propri) a volte rifiuta
# di generare JSON valido quando il destinatario somiglia a un indirizzo
# email reale ("failed_generation": "I'm sorry, but I can't help with
# that."), in modo non deterministico — verificato empiricamente: sullo
# stesso identico prompt, ripetuto 6 volte, ~metà delle chiamate falliva e
# metà andava a buon fine. Non è un errore di configurazione né di prompt,
# quindi la mitigazione è un retry limitato, non una riscrittura del prompt.
# Con un tasso di rifiuto per tentativo del ~50%, 3 tentativi lascerebbero
# ancora ~1 richiesta su 8 fallita; 4 la porta a ~1 su 16.
MAX_ATTEMPTS = 4


def compose_email(user_text: str, context: list[dict], settings: Settings) -> dict:
    if not settings.groq_api_key:
        raise EmailComposeError("GROQ_API_KEY non configurata")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in context[-6:]:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(
                GROQ_URL, json=payload, headers=headers, timeout=settings.external_service_timeout_seconds
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            subject = data["subject"].strip()
            body = data["body"].strip()
            if not subject or not body:
                raise ValueError("oggetto o corpo vuoto")
            return {"subject": subject, "body": body}
        except (requests.RequestException, KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            logger.warning("compose_email tentativo %d/%d fallito: %s", attempt, MAX_ATTEMPTS, exc)

    raise EmailComposeError(f"Groq non ha generato un'email valida dopo {MAX_ATTEMPTS} tentativi: {last_error}")
