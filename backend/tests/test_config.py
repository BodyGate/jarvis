"""Test per il caricamento tipizzato della configurazione (app/config.py)."""
import pytest

from app.config import ConfigError, load_settings


def _clear_relevant_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SECRET_KEY",
        "APP_PASSWORD_HASH",
        "EXTERNAL_SERVICE_TIMEOUT_SECONDS",
        "GROQ_API_KEY",
        "FLASK_ENV",
    ):
        monkeypatch.delenv(var, raising=False)


def test_load_settings_raises_without_secret_key(monkeypatch, tmp_path):
    _clear_relevant_env(monkeypatch)
    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text("", encoding="utf-8")

    with pytest.raises(ConfigError, match="SECRET_KEY"):
        load_settings(env_file=str(empty_env_file))


def test_load_settings_reads_required_and_optional_values(monkeypatch, tmp_path):
    _clear_relevant_env(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text("", encoding="utf-8")

    settings = load_settings(env_file=str(empty_env_file))

    assert settings.secret_key == "test-secret"
    assert settings.groq_api_key == "test-groq-key"
    assert settings.app_password_hash is None
    assert settings.external_service_timeout_seconds == 5.0
    assert settings.is_production is False


def test_load_settings_rejects_timeout_above_5_seconds(monkeypatch, tmp_path):
    _clear_relevant_env(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("EXTERNAL_SERVICE_TIMEOUT_SECONDS", "10")
    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text("", encoding="utf-8")

    with pytest.raises(ConfigError, match="EXTERNAL_SERVICE_TIMEOUT_SECONDS"):
        load_settings(env_file=str(empty_env_file))


def test_load_settings_rejects_non_numeric_timeout(monkeypatch, tmp_path):
    _clear_relevant_env(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("EXTERNAL_SERVICE_TIMEOUT_SECONDS", "not-a-number")
    empty_env_file = tmp_path / ".env"
    empty_env_file.write_text("", encoding="utf-8")

    with pytest.raises(ConfigError, match="EXTERNAL_SERVICE_TIMEOUT_SECONDS"):
        load_settings(env_file=str(empty_env_file))
