"""Caricamento tipizzato della configurazione da variabili d'ambiente.

Nessun segreto è hardcoded in questo modulo: ogni valore proviene da `.env`
(sviluppo locale, ignorato da git) o dalle variabili d'ambiente impostate sulla
piattaforma di hosting (produzione).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Sollevato quando una variabile d'ambiente obbligatoria manca o non è valida."""


@dataclass(frozen=True)
class Settings:
    """Configurazione applicativa, valida per tutta la durata del processo."""

    flask_env: str
    secret_key: str
    app_password_hash: Optional[str]

    supabase_url: Optional[str]
    supabase_key: Optional[str]
    database_url: Optional[str]

    groq_api_key: Optional[str]
    gemini_api_key: Optional[str]
    openweather_api_key: Optional[str]

    google_client_id: Optional[str]
    google_client_secret: Optional[str]
    google_redirect_uri: Optional[str]
    token_encryption_key: Optional[str]

    external_service_timeout_seconds: float

    @property
    def is_production(self) -> bool:
        return self.flask_env == "production"


def load_settings(env_file: Optional[str] = None) -> Settings:
    """Legge `.env` (se presente) e le variabili d'ambiente, e costruisce Settings.

    `secret_key` è sempre obbligatoria: senza di essa Flask non può firmare i
    cookie di sessione e il requisito non negoziabile "nessun endpoint accessibile
    senza sessione valida" (ADR-0002) non è rispettabile. Le altre chiavi
    (Groq, Gemini, Google, ecc.) sono opzionali a livello di config: la loro
    assenza viene gestita dal singolo servizio con un fallback esplicito quando
    quel servizio viene effettivamente chiamato (requisito non negoziabile #3),
    non con un crash all'avvio dell'app.
    """
    load_dotenv(dotenv_path=env_file, override=False)

    secret_key = os.getenv("SECRET_KEY", "")
    if not secret_key:
        raise ConfigError(
            "SECRET_KEY mancante. Genera una chiave con: "
            "python -c \"import secrets; print(secrets.token_hex(32))\" "
            "e impostala in .env (vedi .env.example)."
        )

    timeout_raw = os.getenv("EXTERNAL_SERVICE_TIMEOUT_SECONDS", "5")
    try:
        timeout = float(timeout_raw)
    except ValueError as exc:
        raise ConfigError(
            f"EXTERNAL_SERVICE_TIMEOUT_SECONDS non è un numero valido: {timeout_raw!r}"
        ) from exc
    if timeout <= 0 or timeout > 5:
        raise ConfigError(
            "EXTERNAL_SERVICE_TIMEOUT_SECONDS deve essere tra 0 (escluso) e 5 secondi "
            "(requisito non negoziabile: timeout massimo 5s per servizi esterni)."
        )

    return Settings(
        flask_env=os.getenv("FLASK_ENV", "development"),
        secret_key=secret_key,
        app_password_hash=os.getenv("APP_PASSWORD_HASH") or None,
        supabase_url=os.getenv("SUPABASE_URL") or None,
        supabase_key=os.getenv("SUPABASE_KEY") or None,
        database_url=os.getenv("DATABASE_URL") or None,
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        openweather_api_key=os.getenv("OPENWEATHER_API_KEY") or None,
        google_client_id=os.getenv("GOOGLE_CLIENT_ID") or None,
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET") or None,
        google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI") or None,
        token_encryption_key=os.getenv("TOKEN_ENCRYPTION_KEY") or None,
        external_service_timeout_seconds=timeout,
    )
