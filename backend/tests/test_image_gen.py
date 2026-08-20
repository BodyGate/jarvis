"""Test per la generazione immagini via Pollinations.ai (specialist "image_generate")."""
from unittest.mock import Mock, patch

import pytest
import requests

from app.config import Settings
from app.image_gen import ImageGenError, generate_image


def _settings():
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
        token_encryption_key=None,
        external_service_timeout_seconds=5,
    )


def test_generate_image_returns_bytes():
    settings = _settings()
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.content = b"fake-jpeg-bytes"

    with patch("app.image_gen.requests.get", return_value=mock_response) as mock_get:
        result = generate_image("a cute cat astronaut", settings)

    assert result == b"fake-jpeg-bytes"
    called_url = mock_get.call_args.args[0]
    assert "a%20cute%20cat%20astronaut" in called_url


def test_generate_image_raises_on_network_error():
    settings = _settings()
    with patch("app.image_gen.requests.get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(ImageGenError):
            generate_image("un gatto", settings)


def test_generate_image_raises_on_http_error():
    settings = _settings()
    mock_response = Mock()
    mock_response.raise_for_status = Mock(side_effect=requests.HTTPError("503"))

    with patch("app.image_gen.requests.get", return_value=mock_response):
        with pytest.raises(ImageGenError):
            generate_image("un gatto", settings)
