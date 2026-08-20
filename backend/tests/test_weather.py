"""Test per l'integrazione meteo (RF-012, specialist "weather")."""
from unittest.mock import Mock, patch

import pytest
import requests

from app.config import Settings
from app.weather import WeatherError, get_weather


def _settings(openweather_api_key="test-key"):
    return Settings(
        flask_env="development",
        secret_key="s",
        app_password_hash=None,
        supabase_url=None,
        supabase_key=None,
        database_url=None,
        groq_api_key=None,
        gemini_api_key=None,
        openweather_api_key=openweather_api_key,
        google_client_id=None,
        google_client_secret=None,
        google_redirect_uri=None,
        token_encryption_key=None,
        external_service_timeout_seconds=5,
    )


def _weather_response(status_code=200, name="Roma", temp=26.8, description="cielo sereno"):
    mock = Mock()
    mock.status_code = status_code
    mock.raise_for_status = Mock()
    mock.json.return_value = {
        "name": name,
        "main": {"temp": temp},
        "weather": [{"description": description}],
    }
    return mock


def test_get_weather_tries_italy_bias_first():
    settings = _settings()
    with patch("app.weather.requests.get") as mock_get:
        mock_get.return_value = _weather_response()
        result = get_weather("Roma", settings)

    assert result == {"city": "Roma", "temp": 27, "description": "cielo sereno"}
    called_params = mock_get.call_args.kwargs["params"]
    assert called_params["q"] == "Roma,IT"


def test_get_weather_falls_back_without_country_bias_on_404():
    settings = _settings()
    responses = [Mock(status_code=404), _weather_response(name="Paris", temp=18.0, description="nuvoloso")]
    with patch("app.weather.requests.get", side_effect=responses):
        result = get_weather("Parigi", settings)

    assert result["city"] == "Paris"


def test_get_weather_raises_without_api_key():
    settings = _settings(openweather_api_key=None)
    with pytest.raises(WeatherError):
        get_weather("Roma", settings)


def test_get_weather_raises_without_city():
    settings = _settings()
    with pytest.raises(WeatherError):
        get_weather("", settings)


def test_get_weather_raises_on_network_error():
    settings = _settings()
    with patch("app.weather.requests.get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(WeatherError):
            get_weather("Roma", settings)
