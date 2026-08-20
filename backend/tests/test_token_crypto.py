"""Test per la cifratura AES-256-GCM dei token OAuth (sezione 11.3)."""
import pytest

from app.config import Settings
from app.token_crypto import TokenCryptoError, decrypt_token, encrypt_token

VALID_KEY = "0" * 64  # 32 byte hex, valido solo per i test


def _settings(token_encryption_key=VALID_KEY):
    return Settings(
        flask_env="development",
        secret_key="s",
        app_password_hash=None,
        supabase_url=None,
        supabase_key=None,
        database_url=None,
        groq_api_key=None,
        gemini_api_key=None,
        openweather_api_key=None,
        google_client_id=None,
        google_client_secret=None,
        google_redirect_uri=None,
        token_encryption_key=token_encryption_key,
        external_service_timeout_seconds=5,
    )


def test_encrypt_decrypt_roundtrip():
    settings = _settings()
    ciphertext = encrypt_token("un-token-segreto", settings)
    assert ciphertext != "un-token-segreto"
    assert decrypt_token(ciphertext, settings) == "un-token-segreto"


def test_encrypt_produces_different_ciphertext_each_time():
    settings = _settings()
    c1 = encrypt_token("stesso-token", settings)
    c2 = encrypt_token("stesso-token", settings)
    assert c1 != c2  # nonce casuale


def test_encrypt_raises_without_key():
    settings = _settings(token_encryption_key=None)
    with pytest.raises(TokenCryptoError):
        encrypt_token("token", settings)


def test_encrypt_raises_with_wrong_length_key():
    settings = _settings(token_encryption_key="deadbeef")  # troppo corta
    with pytest.raises(TokenCryptoError):
        encrypt_token("token", settings)


def test_decrypt_raises_on_tampered_ciphertext():
    settings = _settings()
    ciphertext = encrypt_token("token", settings)
    tampered = ciphertext[:-4] + "aaaa"
    with pytest.raises(TokenCryptoError):
        decrypt_token(tampered, settings)


def test_decrypt_raises_with_wrong_key():
    settings = _settings()
    ciphertext = encrypt_token("token", settings)
    other_settings = _settings(token_encryption_key="1" * 64)
    with pytest.raises(TokenCryptoError):
        decrypt_token(ciphertext, other_settings)
