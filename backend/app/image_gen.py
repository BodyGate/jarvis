"""Generazione immagini (specialist "image_generate") via Pollinations.ai —
servizio pubblico gratuito, nessuna chiave richiesta. Sostituisce la delega
manuale a ChatGPT (richiesta esplicita dell'utente: "anche quando deve
interpellare ChatGPT deve farlo JARVIS in autonomia, non dire a me di
farlo"): JARVIS genera l'immagine da sé, l'utente non deve aprire nessun
altro servizio."""
from __future__ import annotations

import urllib.parse

import requests

from app.config import Settings

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"


class ImageGenError(RuntimeError):
    """Sollevato quando la generazione dell'immagine fallisce."""


def generate_image(prompt: str, settings: Settings) -> bytes:
    encoded = urllib.parse.quote(prompt)
    url = POLLINATIONS_URL.format(prompt=encoded)
    try:
        # Pollinations può metterci più del timeout esterno standard (5s):
        # è un servizio gratuito senza SLA, non un'API a pagamento.
        response = requests.get(url, timeout=max(settings.external_service_timeout_seconds, 30))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ImageGenError(f"Generazione immagine fallita: {exc}") from exc
    return response.content
