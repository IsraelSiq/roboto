"""
Testes — NewsClient (issue #18)
Cobre CryptoPanic, RSS fallback e tratamento de erros.
"""
import pytest
from unittest.mock import patch, MagicMock
from backend.market.news_client import NewsClient


class TestNewsClient:
    def setup_method(self):
        self.client = NewsClient()

    # ----- estrutura básica -----

    def test_instantiation(self):
        assert self.client is not None

    def test_get_news_returns_list(self):
        """get_news deve sempre retornar uma lista (mesmo vazia)."""
        with patch.object(self.client, "_fetch_cryptopanic", return_value=[]) as _cp, \
             patch.object(self.client, "_fetch_rss", return_value=[]) as _rss:
            result = self.client.get_news(keyword="bitcoin", page_size=5)
        assert isinstance(result, list)

    def test_cryptopanic_used_when_available(self):
        """CryptoPanic é a fonte primária — deve ser usada se retornar dados."""
        fake_news = [
            {"title": "Bitcoin alta", "source": "cryptopanic", "published_at": "2026-06-10T10:00:00Z"},
        ]
        with patch.object(self.client, "_fetch_cryptopanic", return_value=fake_news) as _cp, \
             patch.object(self.client, "_fetch_rss", return_value=[]) as _rss:
            result = self.client.get_news(keyword="bitcoin", page_size=5)
        assert len(result) >= 1
        assert result[0]["source"] == "cryptopanic"
        _rss.assert_not_called()

    def test_rss_fallback_when_cryptopanic_empty(self):
        """RSS deve ser usado como fallback quando CryptoPanic retorna vazio."""
        fake_rss = [
            {"title": "BTC RSS", "source": "rss", "published_at": "2026-06-10T09:00:00Z"},
        ]
        with patch.object(self.client, "_fetch_cryptopanic", return_value=[]) as _cp, \
             patch.object(self.client, "_fetch_rss", return_value=fake_rss) as _rss:
            result = self.client.get_news(keyword="bitcoin", page_size=5)
        assert len(result) >= 1
        assert result[0]["source"] == "rss"

    def test_rss_fallback_on_cryptopanic_exception(self):
        """RSS deve ser ativado se CryptoPanic lancar exceção."""
        fake_rss = [{"title": "Fallback news", "source": "rss", "published_at": "2026-06-10T08:00:00Z"}]
        with patch.object(self.client, "_fetch_cryptopanic", side_effect=Exception("timeout")) as _cp, \
             patch.object(self.client, "_fetch_rss", return_value=fake_rss) as _rss:
            result = self.client.get_news(keyword="bitcoin", page_size=5)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_empty_when_both_fail(self):
        """Deve retornar lista vazia sem lancar exceção quando ambas as fontes falham."""
        with patch.object(self.client, "_fetch_cryptopanic", side_effect=Exception("cp down")), \
             patch.object(self.client, "_fetch_rss", side_effect=Exception("rss down")):
            result = self.client.get_news(keyword="bitcoin", page_size=5)
        assert isinstance(result, list)
        assert result == []

    def test_page_size_respected(self):
        """Não deve retornar mais itens que page_size."""
        many = [{"title": f"news {i}", "source": "cryptopanic", "published_at": "2026-06-10T10:00:00Z"} for i in range(20)]
        with patch.object(self.client, "_fetch_cryptopanic", return_value=many), \
             patch.object(self.client, "_fetch_rss", return_value=[]):
            result = self.client.get_news(keyword="bitcoin", page_size=5)
        assert len(result) <= 5
