"""
Testes — SupabaseClient
Mock completo do supabase-py. Nenhuma chamada real ao banco.
"""
import pytest
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timezone, timedelta


@pytest.fixture
def supabase_client():
    """SupabaseClient com supabase-py completamente mockado."""
    mock_supabase = MagicMock()

    # Configura chain fluente: .table().select().eq().gte().order().limit().execute()
    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.gte.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.insert.return_value = mock_query
    mock_query.upsert.return_value = mock_query
    mock_query.update.return_value = mock_query
    mock_query.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value = mock_query

    with patch("backend.db.supabase_client.create_client", return_value=mock_supabase), \
         patch.dict("os.environ", {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_KEY": "key"}):
        from backend.db.supabase_client import SupabaseClient
        client = SupabaseClient()
        yield client, mock_supabase, mock_query


class TestSupabaseClientSignals:
    def test_save_signal_calls_insert(self, supabase_client):
        client, _, mock_query = supabase_client
        mock_query.execute.return_value = MagicMock(data=[{"id": "sig-1"}])
        signal_id = client.save_signal({
            "symbol": "BTCUSDT", "final": "CALL_FORTE",
            "rsi": 65.0, "current_price": 61000.0,
        })
        assert signal_id == "sig-1"

    def test_get_last_signals_returns_list(self, supabase_client):
        client, _, mock_query = supabase_client
        mock_query.execute.return_value = MagicMock(data=[
            {"symbol": "BTCUSDT", "final_decision": "CALL_FORTE"}
        ])
        result = client.get_last_signals(symbol="BTCUSDT", limit=5)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_last_signals_error_returns_empty(self, supabase_client):
        client, _, mock_query = supabase_client
        mock_query.execute.side_effect = Exception("DB error")
        result = client.get_last_signals(symbol="BTCUSDT")
        assert result == []


class TestSupabaseClientTrades:
    def test_save_trade_calls_upsert(self, supabase_client):
        client, mock_supabase, mock_query = supabase_client
        mock_trade = MagicMock()
        mock_trade.id = "trade-1"
        mock_trade.symbol = "BTCUSDT"
        mock_trade.direction = "CALL"
        mock_trade.strength = "forte"
        mock_trade.entry_price = 61000.0
        mock_trade.exit_price = 62000.0
        mock_trade.pnl_pct = 1.63
        mock_trade.result = "WIN"
        mock_trade.closed_at = None
        client.save_trade(mock_trade)
        mock_query.upsert.assert_called_once()

    def test_get_trades_error_returns_empty(self, supabase_client):
        client, _, mock_query = supabase_client
        mock_query.execute.side_effect = Exception("timeout")
        result = client.get_trades(symbol="BTCUSDT")
        assert result == []


class TestSupabaseClientNewsCache:
    def test_get_cached_news_hit(self, supabase_client):
        """Cache dentro do TTL deve retornar rows."""
        client, _, mock_query = supabase_client
        now = datetime.now(timezone.utc)
        mock_query.execute.return_value = MagicMock(data=[
            {"title": "BTC alta", "sentiment": "positive", "score": 0.85,
             "created_at": now.isoformat()}
        ])
        rows = client.get_cached_news(symbol="BTCUSDT", ttl_minutes=15)
        assert len(rows) == 1
        assert rows[0]["sentiment"] == "positive"

    def test_get_cached_news_miss_returns_empty(self, supabase_client):
        """Cache expirado (nenhuma row dentro do TTL) retorna lista vazia."""
        client, _, mock_query = supabase_client
        mock_query.execute.return_value = MagicMock(data=[])
        rows = client.get_cached_news(symbol="BTCUSDT", ttl_minutes=15)
        assert rows == []

    def test_get_cached_news_error_returns_empty(self, supabase_client):
        """Erro no Supabase retorna lista vazia sem lancar excecao."""
        client, _, mock_query = supabase_client
        mock_query.execute.side_effect = Exception("network error")
        rows = client.get_cached_news(symbol="BTCUSDT", ttl_minutes=15)
        assert rows == []

    def test_cache_news_calls_insert(self, supabase_client):
        client, mock_supabase, mock_query = supabase_client
        articles = [
            {"title": "BTC alta", "description": "desc",
             "source": "Reuters", "url": "http://x.com",
             "sentiment": "positive", "score": 0.85},
        ]
        client.cache_news(symbol="BTCUSDT", articles=articles)
        mock_query.insert.assert_called_once()

    def test_cache_news_error_does_not_raise(self, supabase_client):
        """Erro ao cachear nao deve propagar excecao."""
        client, _, mock_query = supabase_client
        mock_query.execute.side_effect = Exception("insert error")
        client.cache_news(symbol="BTCUSDT", articles=[{"title": "x"}])


class TestSupabaseClientSessions:
    def test_create_session_returns_id(self, supabase_client):
        client, _, mock_query = supabase_client
        mock_query.execute.return_value = MagicMock(data=[{"id": "sess-1"}])
        session_id = client.create_session("BTCUSDT", "5m", 10000.0)
        assert session_id == "sess-1"

    def test_create_session_error_returns_none(self, supabase_client):
        client, _, mock_query = supabase_client
        mock_query.execute.side_effect = Exception("DB down")
        session_id = client.create_session("BTCUSDT", "5m", 10000.0)
        assert session_id is None


class TestSupabaseClientMissingEnv:
    def test_raises_without_env(self):
        """Sem SUPABASE_URL/KEY deve levantar ValueError."""
        with patch.dict("os.environ", {}, clear=True), \
             patch("backend.db.supabase_client.create_client"):
            from importlib import reload
            import backend.db.supabase_client as mod
            with pytest.raises((ValueError, Exception)):
                mod.SupabaseClient()
