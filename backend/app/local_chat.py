"""Risposta locale generica (RF-003, specialist "other"): quando il router
classifica una richiesta come locale ma non rientra in nessuno specialista
dedicato (meteo/ricerca/ora/email/calendario), JARVIS deve comunque
rispondere davvero — non con un segnaposto — usando Groq per la
generazione, come da stack tecnologico (sezione 6.1: "Risposte AI: Groq API
/ Gemini 1.5 Flash"), non solo per il routing.
"""
from __future__ import annotations

import requests

from app.config import Settings
from app.router import GROQ_MODEL, GROQ_URL

SYSTEM_PROMPT = """Sei JARVIS, un assistente personale AI colloquiale e diretto, ispirato al JARVIS di Iron Man.
Rispondi sempre in italiano, in modo conciso e naturale (2-4 frasi, a meno che l'utente chieda esplicitamente qualcosa di più lungo).
Non hai accesso in tempo reale a meteo, email, calendario o ricerca web in questa risposta: se l'utente te lo chiede esplicitamente, invitalo a riformulare la richiesta in modo più diretto (es. "che tempo fa a Roma")."""


class LocalChatError(RuntimeError):
    """Sollevato quando la generazione della risposta locale fallisce."""


def generate_reply(text: str, context: list[dict], settings: Settings) -> str:
    if not settings.groq_api_key:
        raise LocalChatError("GROQ_API_KEY non configurata")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in context[-10:]:
        role = "user" if msg.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": text})

    payload = {"model": GROQ_MODEL, "messages": messages, "temperature": 0.7}
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    try:
        response = requests.post(
            GROQ_URL, json=payload, headers=headers, timeout=settings.external_service_timeout_seconds
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LocalChatError(f"Chiamata a Groq fallita: {exc}") from exc

    try:
        return response.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise LocalChatError(f"Risposta Groq non valida: {exc}") from exc
