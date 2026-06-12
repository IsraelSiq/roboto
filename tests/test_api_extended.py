"""
Testes — FastAPI endpoints (cobertura extendida, #16)
Cobre: /signals, /trades, /warmup, /bot/start, auth Bearer, /metrics, /status finbert_loaded
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    from backend.api.routes import app
    return TestClient(app)


class TestAPIWarmup:
    def test_warmup_when_not_loaded(self, client):
        with patch("backend.api.routes._get_sentiment_analyzer") as mock_factory:
            mock_analyzer = MagicMock()
            mock_analyzer.is_model_loaded = False
            mock_factory.return_value = mock_analyzer
            r = client.get("/warmup")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "warming_up"
        assert data["finbert_loaded"] is False

    def test_warmup_already_loaded(self, client):
        with patch("backend.api.routes._get_sentiment_analyzer") as mock_factory:
            mock_analyzer = MagicMock()
            mock_analyzer.is_model_loaded = True
            mock_factory.return_value = mock_analyzer
            r = client.get("/warmup")
        assert r.status_code == 200
        assert r.json()["status"] == "already_loaded"
        assert r.json()["finbert_loaded"] is True


class TestAPISignals:
    def test_signals_supabase_unavailable(self, client):
        with patch("backend.api.routes._get_db", return_value=None):
            r = client.get("/signals?symbol=BTCUSDT&limit=10")
        assert r.status_code == 503

    def test_signals_returns_list(self, client):
        mock_db = MagicMock()
        mock_db.get_last_signals.return_value = [
            {"symbol": "BTCUSDT", "final_decision": "CALL_FORTE"}
        ]
        with patch("backend.api.routes._get_db", return_value=mock_db):
            r = client.get("/signals?symbol=BTCUSDT&limit=5")
        assert r.status_code == 200
        assert "signals" in r.json()
        assert len(r.json()["signals"]) == 1


class TestAPITrades:
    def test_trades_no_bot(self, client):
        with patch("backend.api.routes._bot", None):
            r = client.get("/trades")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_trades_history_supabase_unavailable(self, client):
        with patch("backend.api.routes._get_db", return_value=None):
            r = client.get("/trades/history")
        assert r.status_code == 503

    def test_trades_history_returns_data(self, client):
        mock_db = MagicMock()
        mock_db.get_trades.return_value = [{"id": "abc", "direction": "CALL"}]
        with patch("backend.api.routes._get_db", return_value=mock_db):
            r = client.get("/trades/history?symbol=BTCUSDT")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestAPIBotStart:
    def test_bot_start_creates_thread(self, client):
        import threading

        with patch("backend.api.routes._API_TOKEN", None), \
             patch("backend.api.routes._bot", None), \
             patch("backend.api.routes._bot_thread", None), \
             patch("backend.core.bot.BinanceClient"), \
             patch("backend.core.bot.SentimentAnalyzer"), \
             patch("backend.core.bot.TelegramAlert"), \
             patch("backend.api.routes.RobotoBot") as MockBot:

            mock_instance = MagicMock()
            mock_instance._running = False
            MockBot.return_value = mock_instance

            with patch("threading.Thread") as mock_thread_cls:
                mock_thread = MagicMock()
                mock_thread_cls.return_value = mock_thread

                r = client.post("/bot/start", json={
                    "symbol": "BTCUSDT",
                    "interval": "5m",
                    "balance": 10000.0,
                    "only_strong": True,
                })

        assert r.status_code == 200
        assert r.json()["status"] in ("started", "already_running")

    def test_bot_start_already_running(self, client):
        mock_bot = MagicMock()
        mock_bot._running = True
        mock_bot.symbol = "BTCUSDT"
        with patch("backend.api.routes._API_TOKEN", None), \
             patch("backend.api.routes._bot", mock_bot):
            r = client.post("/bot/start", json={
                "symbol": "BTCUSDT", "interval": "5m",
                "balance": 10000.0, "only_strong": True,
            })
        assert r.status_code == 200
        assert r.json()["status"] == "already_running"


class TestAPIAuth:
    def test_stop_without_token_when_api_token_set(self, client):
        with patch("backend.api.routes._API_TOKEN", "secret123"):
            r = client.post("/bot/stop")
        assert r.status_code == 401

    def test_stop_with_correct_token(self, client):
        mock_bot = MagicMock()
        mock_bot._running = True
        with patch("backend.api.routes._API_TOKEN", "secret123"), \
             patch("backend.api.routes._bot", mock_bot):
            r = client.post(
                "/bot/stop",
                headers={"Authorization": "Bearer secret123"},
            )
        assert r.status_code == 200

    def test_stop_with_wrong_token(self, client):
        with patch("backend.api.routes._API_TOKEN", "secret123"):
            r = client.post(
                "/bot/stop",
                headers={"Authorization": "Bearer wrong_token"},
            )
        assert r.status_code == 401


class TestAPIMetrics:
    def test_metrics_no_trades(self, client):
        with patch("backend.api.routes._bot", None):
            r = client.get("/metrics")
        assert r.status_code == 200
        assert r.json()["metrics"] is None


class TestAPIStatusFinbert:
    def test_status_includes_finbert_loaded(self, client):
        with patch("backend.api.routes._get_sentiment_analyzer") as mock_factory:
            mock_analyzer = MagicMock()
            mock_analyzer.is_model_loaded = False
            mock_factory.return_value = mock_analyzer
            r = client.get("/status")
        assert r.status_code == 200
        assert "finbert_loaded" in r.json()
