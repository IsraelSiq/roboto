"""
tests/test_news_impact.py
Testes unitários para:
    - NewsClient (cryptocurrency.cv + RSS fallback)
    - NewsImpactCollector (collect + backfill)
    - SupabaseClient — métodos de news_impact
    - SentimentAnalyzer — exposição de last_news (#52)

Todos os testes rodam sem dependências externas (mocks para HTTP, Binance, Supabase).
"""

import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _news_id(title: str) -> str:
    """Replica a função _news_id do collector para usar nos asserts."""
    return hashlib.sha256(title[:200].encode()).hexdigest()[:40]


def _make_news(title="BNB pumps 10%", source="CoinDesk", published_at="2026-06-01T10:00:00Z"):
    return {"title": title, "description": "desc", "source": source, "published_at": published_at}


# ===========================================================================
# NewsClient
# ===========================================================================

class TestNewsClientCryptocurrencyCV:
    """Testa integração com cryptocurrency.cv."""

    def test_get_news_returns_parsed_items(self):
        from backend.market.news_client import NewsClient

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"title": "BNB sobe 5%", "description": "Detalhes", "published_at": "2026-06-01T10:00:00Z", "source": "CoinDesk"},
                {"title": "BNB cai após hack", "description": "", "published_at": None, "source": "CoinTelegraph"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.market.news_client.requests.get", return_value=mock_resp):
            client = NewsClient(cache_ttl=0)
            result = client.get_news(keyword="bnb", limit=10)

        assert len(result) == 2
        assert result[0]["title"] == "BNB sobe 5%"
        assert result[0]["published_at"] == "2026-06-01T10:00:00Z"
        assert result[0]["source"] == "CoinDesk"
        assert result[1]["published_at"] is None

    def test_get_news_respects_limit(self):
        from backend.market.news_client import NewsClient

        items = [{"title": f"News {i}", "description": "", "published_at": None, "source": "X"} for i in range(20)]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": items}
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.market.news_client.requests.get", return_value=mock_resp):
            client = NewsClient(cache_ttl=0)
            result = client.get_news(keyword="bnb", limit=5)

        assert len(result) == 5

    def test_get_news_skips_empty_titles(self):
        from backend.market.news_client import NewsClient

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"title": "", "description": "sem título", "published_at": None, "source": "X"},
                {"title": "   ", "description": "", "published_at": None, "source": "X"},
                {"title": "BNB valid", "description": "", "published_at": None, "source": "X"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.market.news_client.requests.get", return_value=mock_resp):
            client = NewsClient(cache_ttl=0)
            result = client.get_news(keyword="bnb", limit=10)

        assert len(result) == 1
        assert result[0]["title"] == "BNB valid"

    def test_get_historical_news(self):
        from backend.market.news_client import NewsClient

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"title": "Histórico BNB", "description": "", "published_at": "2026-05-15T08:00:00Z", "source": "CV"}]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.market.news_client.requests.get", return_value=mock_resp) as mock_get:
            client = NewsClient()
            result = client.get_historical_news("bnb", "2026-05-01", "2026-05-31")

        assert len(result) == 1
        assert result[0]["title"] == "Histórico BNB"
        # Verifica que os parâmetros de data foram passados
        call_kwargs = mock_get.call_args
        params = call_kwargs[1].get("params") or call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1].get("params", {})
        assert "from" in str(call_kwargs)


class TestNewsClientRSSFallback:
    """Testa fallback para RSS quando cryptocurrency.cv falha."""

    def test_falls_back_to_rss_on_cv_failure(self):
        from backend.market.news_client import NewsClient

        rss_content = b"""<?xml version="1.0"?>
        <rss><channel>
            <item><title>BNB news from RSS</title><description>desc</description><pubDate>Fri, 01 Jun 2026 10:00:00 +0000</pubDate></item>
        </channel></rss>"""

        cv_resp = MagicMock()
        cv_resp.raise_for_status.side_effect = Exception("timeout")

        rss_resp = MagicMock()
        rss_resp.content = rss_content
        rss_resp.raise_for_status = MagicMock()

        def side_effect(url, **kwargs):
            if "cryptocurrency.cv" in url:
                raise Exception("timeout")
            return rss_resp

        with patch("backend.market.news_client.requests.get", side_effect=side_effect):
            client = NewsClient(cache_ttl=0)
            result = client.get_news(keyword="bnb", limit=5)

        assert len(result) >= 1
        assert result[0]["title"] == "BNB news from RSS"

    def test_cache_hit_avoids_http(self):
        from backend.market.news_client import NewsClient

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"title": "Cached news", "description": "", "published_at": None, "source": "X"}]}
        mock_resp.raise_for_status = MagicMock()

        with patch("backend.market.news_client.requests.get", return_value=mock_resp) as mock_get:
            client = NewsClient(cache_ttl=300)
            client.get_news(keyword="bnb", limit=5)  # popula cache
            client.get_news(keyword="bnb", limit=5)  # deve usar cache

        # Só 1 chamada HTTP — segunda veio do cache
        assert mock_get.call_count == 1


# ===========================================================================
# NewsImpactCollector
# ===========================================================================

class TestNewsImpactCollectorCollect:
    """Testa o método collect()."""

    def _make_collector(self, insert_returns=True):
        from backend.market.news_impact_collector import NewsImpactCollector
        mock_binance = MagicMock()
        mock_db = MagicMock()
        mock_db.insert_news_impact.return_value = insert_returns
        return NewsImpactCollector(mock_binance, mock_db), mock_db

    def test_collect_inserts_correct_payload(self):
        collector, mock_db = self._make_collector()
        news = _make_news("BNB breaks ATH")

        ok = collector.collect(
            news=news,
            symbol="BNBUSDT",
            keyword="bnb",
            sentiment_signal="positive",
            sentiment_score=0.82,
            price_now=650.0,
        )

        assert ok is True
        mock_db.insert_news_impact.assert_called_once()
        payload = mock_db.insert_news_impact.call_args[0][0]
        assert payload["symbol"] == "BNBUSDT"
        assert payload["keyword"] == "bnb"
        assert payload["title"] == "BNB breaks ATH"
        assert payload["sentiment_signal"] == "positive"
        assert payload["sentiment_score"] == 0.82
        assert payload["price_at_news"] == 650.0
        assert payload["news_id"] == _news_id("BNB breaks ATH")
        # price_1h não deve estar no payload (preenchido pelo backfill)
        assert "price_1h" not in payload

    def test_collect_ignores_empty_title(self):
        collector, mock_db = self._make_collector()
        ok = collector.collect(
            news={"title": "", "source": "X"},
            symbol="BNBUSDT", keyword="bnb",
            sentiment_signal="neutral", sentiment_score=0.5, price_now=600.0,
        )
        assert ok is False
        mock_db.insert_news_impact.assert_not_called()

    def test_collect_deduplication_via_news_id(self):
        """Mesma notícia deve gerar mesmo news_id."""
        from backend.market.news_impact_collector import _news_id as nid
        title = "BNB pumps after Binance announcement"
        assert nid(title) == nid(title)  # determinístico
        assert nid(title) != nid("Outro titulo")

    def test_collect_returns_false_on_db_error(self):
        collector, mock_db = self._make_collector(insert_returns=False)
        ok = collector.collect(
            news=_make_news(), symbol="BNBUSDT", keyword="bnb",
            sentiment_signal="positive", sentiment_score=0.7, price_now=620.0,
        )
        assert ok is False


class TestNewsImpactCollectorBackfill:
    """Testa o método backfill_impacts()."""

    def _make_collector(self, pending_rows, price_return=660.0):
        from backend.market.news_impact_collector import NewsImpactCollector
        import pandas as pd

        mock_binance = MagicMock()
        df = pd.DataFrame({"close": [price_return]})
        mock_binance.get_candles.return_value = df

        mock_db = MagicMock()
        mock_db.get_news_impact_pending_backfill.return_value = pending_rows
        mock_db.update_news_impact.return_value = True

        return NewsImpactCollector(mock_binance, mock_db, min_age_hours=1.1), mock_db

    def _row(self, age_hours=2.0, price_at_news=600.0, signal="positive"):
        collected_at = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
        return {
            "id": "uuid-001",
            "collected_at": collected_at,
            "price_at_news": price_at_news,
            "sentiment_signal": signal,
        }

    def test_backfill_updates_price_1h(self):
        row = self._row(age_hours=2.0, price_at_news=600.0)
        collector, mock_db = self._make_collector([row], price_return=660.0)

        updated = collector.backfill_impacts("BNBUSDT")

        assert updated == 1
        mock_db.update_news_impact.assert_called_once()
        patch_dict = mock_db.update_news_impact.call_args[0][1]
        assert "price_1h" in patch_dict
        assert patch_dict["price_1h"] == 660.0
        expected_impact = round((660.0 - 600.0) / 600.0 * 100, 4)
        assert patch_dict["impact_pct_1h"] == pytest.approx(expected_impact)

    def test_backfill_direction_confirmed_positive(self):
        row = self._row(age_hours=2.0, price_at_news=600.0, signal="positive")
        collector, mock_db = self._make_collector([row], price_return=660.0)  # subiu

        collector.backfill_impacts("BNBUSDT")
        patch_dict = mock_db.update_news_impact.call_args[0][1]
        assert patch_dict["direction_confirmed_1h"] is True

    def test_backfill_direction_confirmed_negative_wrong_direction(self):
        row = self._row(age_hours=2.0, price_at_news=600.0, signal="negative")
        collector, mock_db = self._make_collector([row], price_return=660.0)  # subiu mas sinal era negativo

        collector.backfill_impacts("BNBUSDT")
        patch_dict = mock_db.update_news_impact.call_args[0][1]
        assert patch_dict["direction_confirmed_1h"] is False

    def test_backfill_skips_too_recent_rows(self):
        """Registro com < min_age_hours não deve ser backfillado."""
        row = self._row(age_hours=0.5)  # muito novo
        collector, mock_db = self._make_collector([row])

        updated = collector.backfill_impacts("BNBUSDT")

        assert updated == 0
        mock_db.update_news_impact.assert_not_called()

    def test_backfill_returns_zero_on_empty_pending(self):
        collector, mock_db = self._make_collector([])
        updated = collector.backfill_impacts("BNBUSDT")
        assert updated == 0

    def test_backfill_only_1h_when_age_is_between_1_and_4(self):
        """Com 2h de idade só price_1h deve ser preenchido (não price_4h)."""
        row = self._row(age_hours=2.0, price_at_news=600.0)
        collector, mock_db = self._make_collector([row], price_return=620.0)

        collector.backfill_impacts("BNBUSDT")
        patch_dict = mock_db.update_news_impact.call_args[0][1]
        assert "price_1h" in patch_dict
        assert "price_4h" not in patch_dict
        assert "price_24h" not in patch_dict


# ===========================================================================
# SupabaseClient — métodos news_impact
# ===========================================================================

class TestSupabaseClientNewsImpact:
    """Testa os novos métodos do SupabaseClient usando mock do supabase.Client."""

    def _make_client(self):
        with patch("backend.db.supabase_client.create_client") as mock_create:
            mock_supa = MagicMock()
            mock_create.return_value = mock_supa
            with patch.dict("os.environ", {"SUPABASE_URL": "http://x", "SUPABASE_KEY": "k"}):
                from backend.db.supabase_client import SupabaseClient
                client = SupabaseClient()
                client.client = mock_supa
                return client, mock_supa

    def test_insert_news_impact_calls_upsert(self):
        client, mock_supa = self._make_client()
        chain = MagicMock()
        mock_supa.table.return_value.upsert.return_value.execute.return_value = chain

        payload = {"news_id": "abc123", "symbol": "BNBUSDT", "title": "test", "price_at_news": 600.0}
        ok = client.insert_news_impact(payload)

        assert ok is True
        mock_supa.table.assert_called_with("news_impact")
        mock_supa.table.return_value.upsert.assert_called_once()

    def test_insert_news_impact_returns_false_on_exception(self):
        client, mock_supa = self._make_client()
        mock_supa.table.return_value.upsert.return_value.execute.side_effect = Exception("DB error")

        ok = client.insert_news_impact({"news_id": "x", "symbol": "BNBUSDT", "title": "t", "price_at_news": 1.0})
        assert ok is False

    def test_update_news_impact_calls_update(self):
        client, mock_supa = self._make_client()
        mock_supa.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        ok = client.update_news_impact("uuid-001", {"price_1h": 660.0, "impact_pct_1h": 10.0})

        assert ok is True
        mock_supa.table.assert_called_with("news_impact")

    def test_get_pending_backfill_queries_correct_table(self):
        client, mock_supa = self._make_client()
        chain = MagicMock()
        chain.execute.return_value.data = [
            {"id": "uuid-001", "collected_at": "2026-06-01T10:00:00+00:00",
             "price_at_news": 600.0, "sentiment_signal": "positive"}
        ]
        mock_supa.table.return_value.select.return_value.eq.return_value.is_.return_value \
            .order.return_value.limit.return_value = chain

        rows = client.get_news_impact_pending_backfill("BNBUSDT")

        assert len(rows) == 1
        assert rows[0]["id"] == "uuid-001"
        mock_supa.table.assert_called_with("news_impact")

    def test_get_similar_news_impacts_returns_data(self):
        client, mock_supa = self._make_client()
        chain = MagicMock()
        chain.execute.return_value.data = [
            {"id": "uuid-002", "sentiment_score": 0.80, "impact_pct_1h": 5.2,
             "direction_confirmed_1h": True, "collected_at": "2026-06-01T10:00:00+00:00"}
        ]
        # Simula a chain de queries
        mock_table = mock_supa.table.return_value
        mock_table.select.return_value.eq.return_value.eq.return_value \
            .gte.return_value.lte.return_value.not_.is_.return_value \
            .order.return_value.limit.return_value = chain

        rows = client.get_similar_news_impacts(
            symbol="BNBUSDT",
            sentiment_signal="positive",
            score_min=0.7,
            score_max=0.9,
            horizon="1h",
        )

        assert len(rows) == 1
        assert rows[0]["impact_pct_1h"] == 5.2


# ===========================================================================
# SentimentAnalyzer — last_news exposto (#52)
# ===========================================================================

class TestSentimentAnalyzerLastNews:
    """Garante que last_news é populado corretamente."""

    def test_last_news_empty_on_init(self):
        from backend.analysis.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer()
        assert analyzer.last_news == []

    def test_last_news_populated_after_news_client_path(self):
        from backend.analysis.sentiment import SentimentAnalyzer

        news_items = [
            {"title": "BNB news 1", "description": "", "published_at": "2026-06-01T10:00:00Z", "source": "CV"},
            {"title": "BNB news 2", "description": "", "published_at": "2026-06-01T11:00:00Z", "source": "CoinDesk"},
        ]

        analyzer = SentimentAnalyzer()
        analyzer._db = False  # força pular cache Supabase

        mock_news_client = MagicMock()
        mock_news_client.get_news.return_value = news_items
        analyzer._news_client = mock_news_client

        # Mocka analyze_news para não carregar FinBERT
        from backend.analysis.sentiment import SentimentResult
        mock_result = SentimentResult(signal="positive", score=0.8, news_count=2, source="finbert")
        analyzer.analyze_news = MagicMock(return_value=mock_result)

        analyzer.get_news_sentiment(keyword="bnb", news_limit=5)

        assert analyzer.last_news == news_items
        assert len(analyzer.last_news) == 2
        assert analyzer.last_news[0]["title"] == "BNB news 1"

    def test_last_news_empty_when_supabase_cache_hit(self):
        """Quando resultado vem do cache Supabase, last_news deve ser []."""
        from backend.analysis.sentiment import SentimentAnalyzer

        analyzer = SentimentAnalyzer()

        mock_db = MagicMock()
        mock_db.get_cached_news.return_value = [
            {"title": "Cached news", "sentiment": "positive", "score": 0.8}
        ]
        analyzer._db = mock_db

        analyzer.get_news_sentiment(keyword="bnb", news_limit=5)

        # Cache hit — last_news permanece vazio
        assert analyzer.last_news == []

    def test_last_news_cleared_on_each_call(self):
        """last_news deve ser resetado no início de cada chamada."""
        from backend.analysis.sentiment import SentimentAnalyzer, SentimentResult

        analyzer = SentimentAnalyzer()
        analyzer._db = False

        news_first = [{"title": "First call", "description": "", "published_at": None, "source": "X"}]
        news_second = []  # segunda chamada sem notícias

        mock_client = MagicMock()
        mock_client.get_news.side_effect = [news_first, news_second]
        analyzer._news_client = mock_client

        mock_result = SentimentResult(signal="neutral", score=0.5, news_count=1, source="finbert")
        analyzer.analyze_news = MagicMock(return_value=mock_result)

        analyzer.get_news_sentiment(keyword="bnb", news_limit=5)
        assert analyzer.last_news == news_first

        analyzer.get_news_sentiment(keyword="bnb", news_limit=5)
        assert analyzer.last_news == []  # segunda chamada retornou vazio
