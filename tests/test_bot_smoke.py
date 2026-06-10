"""
Smoke test — RobotoBot (integração MVP)
Roda o loop completo por 2 ciclos com todos os módulos externos mockados.
"""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
import pandas as pd
import numpy as np


def make_fake_candles(n=120):
    np.random.seed(42)
    close = 60000 + np.cumsum(np.random.randn(n) * 200)
    return pd.DataFrame({
        "open":   close - 100,
        "high":   close + 200,
        "low":    close - 200,
        "close":  close,
        "volume": np.random.uniform(10, 100, n),
    })


@pytest.fixture
def bot_2_cycles():
    from backend.analysis.sentiment import SentimentResult
    from backend.core.bot import RobotoBot

    fake_candles = make_fake_candles()
    mock_binance = MagicMock()
    mock_binance.get_candles.return_value = fake_candles
    mock_binance.get_price.return_value = 61000.0

    mock_sent_instance = MagicMock()
    mock_sent_instance.get_news_sentiment.return_value = SentimentResult(
        signal="neutral", score=0.5, reason="mock"
    )

    mock_tg = MagicMock()
    mock_tg.enabled = False

    # Patcha ANTES de instanciar o bot
    with patch("backend.core.bot.BinanceClient", return_value=mock_binance), \
         patch("backend.core.bot.SentimentAnalyzer", return_value=mock_sent_instance), \
         patch("backend.core.bot.TelegramAlert", return_value=mock_tg):
        bot = RobotoBot(
            symbol="BTCUSDT",
            interval="5m",
            balance=10000.0,
            max_cycles=2,
            sleep_seconds=0,
            use_db=False,
        )
        bot.tg = mock_tg  # garante que o mock está no atributo correto
        yield bot, mock_tg


class TestBotSmoke:
    def test_bot_runs_without_exception(self, bot_2_cycles):
        bot, _ = bot_2_cycles
        bot.run()

    def test_bot_cycles_count(self, bot_2_cycles):
        bot, _ = bot_2_cycles
        bot.run()
        assert bot._cycle == 2

    def test_telegram_startup_called(self, bot_2_cycles):
        bot, mock_tg = bot_2_cycles
        bot.run()
        mock_tg.startup.assert_called_once()

    def test_telegram_shutdown_called(self, bot_2_cycles):
        bot, mock_tg = bot_2_cycles
        bot.run()
        mock_tg.shutdown.assert_called_once()

    def test_bot_not_paused_after_2_cycles(self, bot_2_cycles):
        bot, _ = bot_2_cycles
        bot.run()
        assert not bot.risk.is_paused()

    def test_bot_balance_positive_after_run(self, bot_2_cycles):
        bot, _ = bot_2_cycles
        bot.run()
        assert bot.risk.balance > 0
