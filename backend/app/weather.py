"""Meteo (RF-012, specialist "weather") via OpenWeatherMap, come da stack
tecnologico (sezione 6.3).

Nota: `q=<città>` senza qualificatore di paese può risolvere alla città
sbagliata quando il nome è ambiguo — verificato: `q=Roma` restituiva Rome,
New York (USA) invece di Roma, Italia. Dato che JARVIS risponde in italiano
a un utente italiano, si prova prima con il bias `,IT`; se quella città non
esiste in Italia (404), si ripete la richiesta senza bias per gestire
correttamente città estere (es. "Parigi" non esiste in Italia).
"""
from __future__ import annotations

import requests

from app.config import Settings

WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


class WeatherError(RuntimeError):
    """Sollevato quando la richiesta meteo fallisce (città non trovata, rete, timeout)."""


def _fetch(city_query: str, settings: Settings) -> dict:
    response = requests.get(
        WEATHER_URL,
        params={
            "q": city_query,
            "appid": settings.openweather_api_key,
            "units": "metric",
            "lang": "it",
        },
        timeout=settings.external_service_timeout_seconds,
    )
    return response


def get_weather(city: str, settings: Settings) -> dict:
    if not settings.openweather_api_key:
        raise WeatherError("OPENWEATHER_API_KEY non configurata")
    if not city:
        raise WeatherError("Città non specificata")

    try:
        response = _fetch(f"{city},IT", settings)
        if response.status_code == 404:
            response = _fetch(city, settings)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise WeatherError(f"Chiamata a OpenWeatherMap fallita: {exc}") from exc

    try:
        data = response.json()
        return {
            "city": data["name"],
            "temp": round(data["main"]["temp"]),
            "description": data["weather"][0]["description"],
        }
    except (KeyError, IndexError) as exc:
        raise WeatherError(f"Risposta OpenWeatherMap non valida: {exc}") from exc
