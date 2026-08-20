"""Test per la ricerca web (RF-003, specialist "search")."""
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.search import SearchError, web_search


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


def test_web_search_maps_ddgs_results():
    fake_ddgs = MagicMock()
    fake_ddgs.__enter__.return_value.text.return_value = [
        {"title": "T", "href": "https://example.com", "body": "snippet"}
    ]
    with patch("app.search.DDGS", return_value=fake_ddgs):
        results = web_search("query", _settings())

    assert results == [{"title": "T", "url": "https://example.com", "snippet": "snippet"}]


def test_web_search_raises_search_error_on_ddgs_exception():
    from ddgs.exceptions import RatelimitException

    fake_ddgs = MagicMock()
    fake_ddgs.__enter__.return_value.text.side_effect = RatelimitException("rate limited")
    with patch("app.search.DDGS", return_value=fake_ddgs):
        with pytest.raises(SearchError):
            web_search("query", _settings())
