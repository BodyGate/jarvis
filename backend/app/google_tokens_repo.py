"""Persistenza dei token OAuth Google sulla tabella `google_tokens`
(schema Fase 1), cifrati con AES-256-GCM (`app.token_crypto`) prima di
toccare Supabase — mai in chiaro nel DB (sezione 11.3, requisito non
negoziabile)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import Client

from app.config import Settings
from app.constants import DEFAULT_USER_ID
from app.google_oauth import GoogleOAuthError, refresh_access_token
from app.token_crypto import decrypt_token, encrypt_token


def save_tokens(db: Client, settings: Settings, token: dict) -> None:
    """`token` è il dict ritornato da authlib (fetch_token/refresh_token):
    access_token, refresh_token (assente su un refresh), expires_at/expires_in, scope."""
    expires_at = None
    if token.get("expires_at"):
        expires_at = datetime.fromtimestamp(token["expires_at"], tz=timezone.utc).isoformat()
    elif token.get("expires_in"):
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=token["expires_in"])
        ).isoformat()

    row = {
        "user_id": DEFAULT_USER_ID,
        "provider": "google",
        "access_token": encrypt_token(token["access_token"], settings),
        "expires_at": expires_at,
    }
    if token.get("refresh_token"):
        row["refresh_token"] = encrypt_token(token["refresh_token"], settings)
    if token.get("scope"):
        # Un refresh riuscito spesso non restituisce "scope": senza questo
        # controllo sovrascriveremmo gli scope corretti salvati al primo
        # collegamento con una lista vuota ad ogni rinnovo del token.
        row["scopes"] = token["scope"].split()

    existing = (
        db.table("google_tokens")
        .select("id, refresh_token")
        .eq("user_id", DEFAULT_USER_ID)
        .eq("provider", "google")
        .limit(1)
        .execute()
    )
    if existing.data:
        db.table("google_tokens").update(row).eq("id", existing.data[0]["id"]).execute()
    else:
        if "refresh_token" not in row:
            raise ValueError("Primo collegamento Google senza refresh_token restituito da Google")
        db.table("google_tokens").insert(row).execute()


def get_tokens(db: Client, settings: Settings) -> Optional[dict]:
    result = (
        db.table("google_tokens")
        .select("*")
        .eq("user_id", DEFAULT_USER_ID)
        .eq("provider", "google")
        .limit(1)
        .execute()
    )
    if not result.data:
        return None

    row = result.data[0]
    return {
        "access_token": decrypt_token(row["access_token"], settings),
        "refresh_token": decrypt_token(row["refresh_token"], settings),
        "expires_at": row.get("expires_at"),
        "scopes": row.get("scopes") or [],
    }


def delete_tokens(db: Client) -> None:
    db.table("google_tokens").delete().eq("user_id", DEFAULT_USER_ID).eq(
        "provider", "google"
    ).execute()


def is_expired(expires_at: Optional[str]) -> bool:
    if not expires_at:
        return True
    expiry = datetime.fromisoformat(expires_at)
    return datetime.now(timezone.utc) >= expiry


def ensure_valid_access_token(db: Client, settings: Settings) -> str:
    """Ritorna un access_token valido, rinnovandolo tramite il refresh_token
    se scaduto (sezione 11.3, punto 6: "Refresh automatico")."""
    tokens = get_tokens(db, settings)
    if tokens is None:
        raise GoogleOAuthError("Google non collegato: usa /auth/google per autorizzare l'accesso")

    if not is_expired(tokens["expires_at"]):
        return tokens["access_token"]

    refreshed = refresh_access_token(tokens["refresh_token"], settings)
    save_tokens(db, settings, refreshed)
    return refreshed["access_token"]
