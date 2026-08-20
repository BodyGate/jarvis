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
    """RF-010. `start`/`end` in formato RFC3339. L'API Calendar richiede un
    fuso orario esplicito (offset nella stringa, oppure il campo
    `timeZone`): quando `start`/`end` non lo includono già (nessun `+`, `-`
    dopo l'ora, o `Z` finale), si assume UTC — coerente con il resto del
    progetto, che non ha un fuso orario utente configurabile."""
    start_field = {"dateTime": start}
    end_field = {"dateTime": end}
    if not (start.endswith("Z") or "+" in start[10:] or "-" in start[10:]):
        start_field["timeZone"] = "UTC"
    if not (end.endswith("Z") or "+" in end[10:] or "-" in end[10:]):
        end_field["timeZone"] = "UTC"

    try:
        response = requests.post(
            CALENDAR_BASE,
            headers=_headers(access_token),
            json={
                "summary": summary,
                "description": description,
                "location": location,
                "start": start_field,
                "end": end_field,
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
