"""Memoria a lungo termine (RF-013): fatti duraturi sull'utente (preferenze,
contatti, abitudini, lavoro) estratti dai suoi messaggi e riusati nelle
risposte future. Tabella `user_facts` (schema Fase 1), mai popolata finché
non collegata qui.

L'estrazione è un side-effect best-effort: se fallisce (Groq non
raggiungibile, risposta malformata) non deve mai rompere la chat — si
ignora silenziosamente e si prosegue senza nuovi fatti.
"""
from __future__ import annotations

import json
import logging

import requests
from supabase import Client

from app.config import Settings
from app.constants import DEFAULT_USER_ID
from app.router import GROQ_MODEL, GROQ_URL

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"preference", "contact", "habit", "work"}

EXTRACT_SYSTEM_PROMPT = """Sei il modulo di estrazione fatti di un assistente personale.
Analizza SOLO l'ultimo messaggio dell'utente e stabilisci se contiene un fatto duraturo su di
lui degno di essere ricordato in futuro: preferenze (gusti, cose che ama/odia), contatti
(persone che nomina e chi sono per lui), abitudini, informazioni di lavoro.
Ignora richieste operative, domande, saluti, conversazione superficiale: la maggior parte dei
messaggi non contiene nulla da ricordare, in quel caso rispondi con una lista vuota.

Fatti già noti sull'utente (non ripeterli, a meno che il nuovo messaggio li corregga o li aggiorni):
{known_facts}

Rispondi SOLO con un oggetto JSON in questo formato esatto, senza altro testo:
{{"facts": [{{"category": "preference|contact|habit|work", "fact": "<fatto conciso in italiano, terza persona>", "confidence": <0.0-1.0>}}]}}
Se non c'è nessun fatto nuovo o rilevante, rispondi {{"facts": []}}."""


def _format_known_facts(known_facts: list[dict]) -> str:
    if not known_facts:
        return "(nessuno)"
    return "\n".join(f"- ({f['category']}) {f['fact']}" for f in known_facts)


def extract_facts(user_text: str, known_facts: list[dict], settings: Settings) -> list[dict]:
    """Ritorna una lista (anche vuota) di nuovi fatti: {category, fact, confidence}.
    Non solleva mai eccezioni verso il chiamante — vedi nota di modulo."""
    if not user_text or not settings.groq_api_key:
        return []

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": EXTRACT_SYSTEM_PROMPT.format(known_facts=_format_known_facts(known_facts))},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    try:
        response = requests.post(
            GROQ_URL, json=payload, headers=headers, timeout=settings.external_service_timeout_seconds
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.warning("Estrazione fatti fallita, ignorata: %s", exc)
        return []

    facts = []
    for f in data.get("facts", []):
        category = f.get("category")
        fact_text = (f.get("fact") or "").strip()
        if category not in VALID_CATEGORIES or not fact_text:
            continue
        try:
            confidence = float(f.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        facts.append({"category": category, "fact": fact_text, "confidence": confidence})
    return facts


def save_facts(db: Client, facts: list[dict], source_message_id: str | None) -> None:
    for f in facts:
        db.table("user_facts").insert(
            {
                "user_id": DEFAULT_USER_ID,
                "category": f["category"],
                "fact": f["fact"],
                "confidence": f["confidence"],
                "source_message_id": source_message_id,
            }
        ).execute()


def get_known_facts(db: Client, limit: int = 30) -> list[dict]:
    result = (
        db.table("user_facts")
        .select("category, fact, confidence, created_at")
        .eq("user_id", DEFAULT_USER_ID)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def list_all_facts(db: Client) -> list[dict]:
    """Tutti i fatti memorizzati, per la sezione Libreria — a differenza di
    `get_known_facts` (usata per iniettare contesto nei prompt, quindi
    limitata) qui serve l'elenco completo che l'utente può consultare/gestire."""
    result = (
        db.table("user_facts")
        .select("id, category, fact, confidence, created_at")
        .eq("user_id", DEFAULT_USER_ID)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def delete_fact(db: Client, fact_id: str) -> bool:
    result = (
        db.table("user_facts")
        .delete()
        .eq("id", fact_id)
        .eq("user_id", DEFAULT_USER_ID)
        .execute()
    )
    return bool(result.data)
