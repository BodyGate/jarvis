"""Test per l'analisi immagini (RF-011, flusso 8.4)."""
from unittest.mock import Mock, patch

import pytest
import requests

from app.config import Settings
from app.vision import VisionError, analyze_image

VALID_B64 = "aGVsbG8="  # "hello" in base64


def _settings(gemini_api_key="test-key"):
    return Settings(
        flask_env="development",
        secret_key="s",
        app_password_hash=None,
        supabase_url=None,
        supabase_key=None,
        database_url=None,
        groq_api_key=None,
        gemini_api_key=gemini_api_key,
        openweather_api_key=None,
        google_client_id=None,
        google_client_secret=None,
        google_redirect_uri=None,
        token_encryption_key=None,
        external_service_timeout_seconds=5,
    )


def _gemini_response(text: str) -> Mock:
    mock = Mock()
    mock.raise_for_status = Mock()
    mock.json.return_value = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return mock


def test_analyze_image_returns_text():
    settings = _settings()
    with patch("app.vision.requests.post") as mock_post:
        mock_post.return_value = _gemini_response("È una fattura.")
        result = analyze_image(VALID_B64, settings)

    assert result == "È una fattura."


def test_analyze_image_strips_data_url_prefix():
    settings = _settings()
    with patch("app.vision.requests.post") as mock_post:
        mock_post.return_value = _gemini_response("ok")
        analyze_image(f"data:image/png;base64,{VALID_B64}", settings)

    sent_body = mock_post.call_args.kwargs["json"]
    inline_data = sent_body["contents"][0]["parts"][1]["inline_data"]
    assert inline_data["data"] == VALID_B64
    assert inline_data["mime_type"] == "image/png"


def test_analyze_image_raises_without_api_key():
    settings = _settings(gemini_api_key=None)
    with pytest.raises(VisionError):
        analyze_image(VALID_B64, settings)


def test_analyze_image_raises_on_invalid_base64():
    settings = _settings()
    with pytest.raises(VisionError):
        analyze_image("not-valid-base64!!!", settings)


def test_analyze_image_raises_on_network_error():
    settings = _settings()
    with patch("app.vision.requests.post", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(VisionError):
            analyze_image(VALID_B64, settings)


def test_analyze_image_raises_on_malformed_response():
    settings = _settings()
    with patch("app.vision.requests.post") as mock_post:
        mock = Mock()
        mock.raise_for_status = Mock()
        mock.json.return_value = {"candidates": []}
        mock_post.return_value = mock
        with pytest.raises(VisionError):
            analyze_image(VALID_B64, settings)
