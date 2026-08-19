"""Accesso al client Supabase condiviso dal processo Flask.

Usa sempre la service_role key (mai `anon`): vedi ADR-0004, l'isolamento per
`user_id` è responsabilità del codice applicativo, non di RLS.
"""
from __future__ import annotations

from supabase import Client, create_client

from app.config import ConfigError, Settings

_client: Client | None = None


def get_supabase_client(settings: Settings) -> Client:
    """Ritorna il client Supabase, creandolo alla prima chiamata."""
    global _client
    if _client is None:
        if not settings.supabase_url or not settings.supabase_key:
            raise ConfigError(
                "SUPABASE_URL e SUPABASE_KEY sono obbligatori per usare il "
                "database (vedi .env.example)."
            )
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


def reset_client_cache() -> None:
    """Usato dai test per forzare la ricreazione del client tra un test e l'altro."""
    global _client
    _client = None
