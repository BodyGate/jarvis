"""Ricerca web rapida (RF-003, target "local"). Il documento di progetto
(sezione 6.3) indicava la libreria `duckduckgo-search`; è stata sostituita
da `ddgs`, l'erede attivamente mantenuto — vedi commento in requirements.txt.

DuckDuckGo non ha un'API pubblica ufficiale: `ddgs` fa scraping e può andare
in rate limit senza preavviso (osservato più volte durante lo sviluppo,
nonostante il documento originale indicasse "nessun limite"). Ogni chiamata
è quindi protetta e il fallimento è esposto come SearchError, non come
crash, per lasciare al chiamante la scelta di un messaggio d'errore pulito.
"""
from __future__ import annotations

from ddgs import DDGS
from ddgs.exceptions import DDGSException

from app.config import Settings


class SearchError(RuntimeError):
    """Sollevato quando la ricerca fallisce (rate limit, timeout, errore di rete)."""


def web_search(query: str, settings: Settings, max_results: int = 5) -> list[dict]:
    try:
        with DDGS(timeout=settings.external_service_timeout_seconds) as ddgs:
            results = ddgs.text(query, max_results=max_results)
    except DDGSException as exc:
        raise SearchError(f"Ricerca DuckDuckGo fallita: {exc}") from exc

    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in results
    ]
