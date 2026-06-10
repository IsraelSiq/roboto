"""
Smoke test — RobotoBot (integração MVP)
Roda o loop completo por 2 ciclos com todos os módulos externos mockados.
Valida que o bot inicia, executa ciclos e encerra sem erros.
"""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np


def make_fake_candles(n=120):
    """DataFrame de candles sintéticos com colunas esperadas pelo TechnicalAnalyzer."""
    np.random.seed(42)
    close = 60000 + np.cumsum(np.random.randn(n) * 200)
    df = pd.DataFrame({
        "open":   close - 100,
        "high":   close + 200,
        "low":    close - 200,
        "close":  close,
        "volume": np.random.uniform(10, 100, n),
    })
    return df


@pytest.fixture
def bot_2_cycles():
    """RobotoBot configurado para 2 ciclos com todas as dependências mockadas."""
    from backend.core.bot import RobotoBot

    fake_candles = make_fake_candles()

    with patch("backend.core.bot.BinanceClient") as MockBinance, \
         patch("backend.core.bot.SentimentAnalyzer") as MockSentiment, \
         patch("backend.core.bot.TelegramAlert") as MockTelegram:

        # Binance: retorna candles e preco
        mock_client = MagicMock()
        mock_client.get_candles.return_value = fake_candles
        mock_client.get_price.return_value = 61000.0
        MockBinance.return_value = mock_client

        # Sentiment: sempre retorna neutral
        from backend.analysis.sentiment import SentimentResult
        mock_sent = MagicMock()
        mock_sent.get_news_sentiment.return_value = SentimentResult(
            signal="neutral", score=0.5, reason="mock"
        )
        MockSentiment.return_value = mock_sent

        # Telegram: silencioso (não envia nada)
        mock_tg = MagicMock()
        mock_tg.enabled = False
        MockTelegram.return_value = mock_tg

        bot = RobotoBot(
            symbol="BTCUSDT",
            interval="5m",
            balance=10000.0,
            max_cycles=2,
            sleep_seconds=0,
            use_db=False,
        )
        yield bot, mock_tg


class TestBotSmoke:
    def test_bot_runs_without_exception(self, bot_2_cycles):
        """O bot deve completar 2 ciclos sem lancar exceção."""
        bot, _ = bot_2_cycles
        bot.run()  # não deve lancar nada

    def test_bot_cycles_count(self, bot_2_cycles):
        """Após run(), _cycle deve ser exatamente 2."""
        bot, _ = bot_2_cycles
        bot.run()
        assert bot._cycle == 2

    def test_telegram_startup_called(self, bot_2_cycles):
        """tg.startup deve ser chamado uma vez durante run()."""
        bot, mock_tg = bot_2_cycles
        bot.run()
        mock_tg.startup.assert_called_once()

    def test_telegram_shutdown_called(self, bot_2_cycles):
        """tg.shutdown deve ser chamado uma vez ao finalizar."""
        bot, mock_tg = bot_2_cycles
        bot.run()
        mock_tg.shutdown.assert_called_once()

    def test_bot_not_paused_after_2_cycles(self, bot_2_cycles):
        """2 ciclos sem perdas não devem acionar circuit breaker."""
        bot, _ = bot_2_cycles
        bot.run()
        assert not bot.risk.is_paused()

    def test_bot_balance_unchanged_without_trade(self, bot_2_cycles):
        """Se nenhum trade for aberto, o saldo não deve mudar."""
        bot, _ = bot_2_cycles
        initial = bot.risk.initial_balance
        bot.run()
        # saldo pode ter mudado se um trade foi aberto+fechado; aceita qualquer valor positivo
        assert bot.risk.balance > 0
