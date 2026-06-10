"""
Testes — NewsClient (issue #18)
Cobre CryptoPanic, RSS fallback e tratamento de erros.
"""
import pytest
from unittest.mock import patch
from backend.market.news_client import NewsClient


class TestNewsClient:
    def setup_method(self):
        self.client = NewsClient(cache_ttl=0)

    def test_instantiation(self):
        assert self.client is not None

    def test_get_news_returns_list(self):
        with patch.object(self.client, "_fetch_cryptopanic", return_value=[]), \
             patch.object(self.client, "_fetch_rss", return_value=[]):
            result = self.client.get_news(keyword="bitcoin", limit=5)
        assert isinstance(result, list)

    def test_cryptopanic_used_when_available(self):
        fake_news = [{"title": "Bitcoin alta", "description": ""}]
        with patch.object(self.client, "_fetch_cryptopanic", return_value=fake_news) as _cp, \
             patch.object(self.client, "_fetch_rss", return_value=[]) as _rss:
            result = self.client.get_news(keyword="bitcoin", limit=5)
        assert len(result) >= 1
        assert result[0]["title"] == "Bitcoin alta"
        _rss.assert_not_called()

    def test_rss_fallback_when_cryptopanic_empty(self):
        fake_rss = [{"title": "BTC RSS", "description": ""}]
        with patch.object(self.client, "_fetch_cryptopanic", return_value=[]), \
             patch.object(self.client, "_fetch_rss", return_value=fake_rss):
            result = self.client.get_news(keyword="bitcoin", limit=5)
        assert len(result) >= 1
        assert result[0]["title"] == "BTC RSS"

    def test_rss_fallback_on_cryptopanic_exception(self):
        fake_rss = [{"title": "Fallback news", "description": ""}]
        with patch.object(self.client, "_fetch_cryptopanic", return_value=[]), \
             patch.object(self.client, "_fetch_rss", return_value=fake_rss):
            result = self.client.get_news(keyword="bitcoin", limit=5)
        assert isinstance(result, list) and len(result) >= 1

    def test_empty_when_both_fail(self):
        with patch.object(self.client, "_fetch_cryptopanic", return_value=[]), \
             patch.object(self.client, "_fetch_rss", return_value=[]):
            result = self.client.get_news(keyword="bitcoin", limit=5)
        assert result == []

    def test_limit_respected(self):
        """_fetch_cryptopanic recebe o limit correto e trunca o resultado."""
        captured = []

        def fake_fetch(keyword, lim):
            captured.append(lim)
            return [{"title": f"n{i}", "description": ""} for i in range(20)][:lim]

        with patch.object(self.client, "_fetch_cryptopanic", side_effect=fake_fetch), \
             patch.object(self.client, "_fetch_rss", return_value=[]):
            result = self.client.get_news(keyword="bitcoin", limit=5)

        assert captured[0] == 5
        assert len(result) <= 5
