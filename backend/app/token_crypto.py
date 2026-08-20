"""Crittografia AES-256-GCM per i token OAuth Google (sezione 11.3, requisito
non negoziabile: nessun segreto in chiaro nel DB — vedi tabella
`google_tokens`, colonne `access_token`/`refresh_token`).

Formato del testo cifrato memorizzato: base64(nonce[12 byte] || ciphertext).
Un nonce casuale per ogni cifratura, come richiesto da AES-GCM.
"""
from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings

_NONCE_SIZE = 12


class TokenCryptoError(RuntimeError):
    """Sollevato quando manca la chiave di cifratura o la decifratura fallisce."""


def _get_key(settings: Settings) -> bytes:
    if not settings.token_encryption_key:
        raise TokenCryptoError("TOKEN_ENCRYPTION_KEY non configurata")
    try:
        key = bytes.fromhex(settings.token_encryption_key)
    except ValueError as exc:
        raise TokenCryptoError("TOKEN_ENCRYPTION_KEY non è esadecimale valido") from exc
    if len(key) != 32:
        raise TokenCryptoError(
            f"TOKEN_ENCRYPTION_KEY deve essere 32 byte (64 caratteri hex), trovati {len(key)}"
        )
    return key


def encrypt_token(plaintext: str, settings: Settings) -> str:
    key = _get_key(settings)
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_token(encoded: str, settings: Settings) -> str:
    key = _get_key(settings)
    try:
        raw = base64.b64decode(encoded, validate=True)
        nonce, ciphertext = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    except (binascii.Error, InvalidTag, ValueError) as exc:
        raise TokenCryptoError(f"Impossibile decifrare il token: {exc}") from exc
    return plaintext.decode("utf-8")
