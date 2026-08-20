"""Integrazione Google Calendar (RF-009, RF-010). Nome del modulo
`calendar_service` per non entrare in conflitto con `calendar` della
libreria standard."""
from __future__ import annotations

import requests

from app.config import Settings

CALENDAR_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


class CalendarError(RuntimeError):
    """Sollevato quando una chiamata all'API Calendar fallisce."""


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def list_events(access_token: str, settings: Settings, time_min: str, time_max: str) -> list[dict]:
    """RF-009. `time_min`/`time_max` in formato RFC3339 (es. 2026-08-22T00:00:00Z)."""
    try:
        response = requests.get(
            CALENDAR_BASE,
            headers=_headers(access_token),
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
            },
            timeout=settings.external_service_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CalendarError(f"Lettura calendario fallita: {exc}") from exc

    items = response.json().get("items", [])
    return [
        {
            "id": e["id"],
            "summary": e.get("summary", ""),
            "description": e.get("description", ""),
            "location": e.get("location", ""),
            "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
            "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
        }
        for e in items
    ]


def create_event(
    access_token: str,
    settings: Settings,
    *,
    summary: str,
    start: str,
    end: str,
    location: str = "",
    description: str = "",
) -> str:
    """RF-010. `start`/`end` in formato RFC3339 con timezone."""
    try:
        response = requests.post(
            CALENDAR_BASE,
            headers=_headers(access_token),
            json={
                "summary": summary,
                "description": description,
                "location": location,
                "start": {"dateTime": start},
                "end": {"dateTime": end},
            },
            timeout=settings.external_service_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CalendarError(f"Creazione evento fallita: {exc}") from exc

    return response.json()["id"]


def delete_event(access_token: str, event_id: str, settings: Settings) -> None:
    try:
        response = requests.delete(
            f"{CALENDAR_BASE}/{event_id}",
            headers=_headers(access_token),
            timeout=settings.external_service_timeout_seconds,
        )
        if response.status_code not in (200, 204, 404):
            response.raise_for_status()
    except requests.RequestException as exc:
        raise CalendarError(f"Cancellazione evento fallita: {exc}") from exc
