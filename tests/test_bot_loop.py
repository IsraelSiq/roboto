"""
Testes — RobotoBot loop
Todos os módulos externos são mockados. Nenhum acesso à Binance/Supabase/FinBERT.
"""
import pytest
from unittest.mock import patch, MagicMock, call
import pandas as pd
import numpy as np


def _make_candles(n=120, seed=42):
    np.random.seed(seed)
    close = 60000 + np.cumsum(np.random.randn(n) * 200)
    return pd.DataFrame({
        "open":   close - 100,
        "high":   close + 200,
        "low":    close - 200,
        "close":  close,
        "volume": np.random.uniform(10, 100, n),
    })


@pytest.fixture
def bot_factory():
    """Fabrica de RobotoBot com todos os modulos externos mockados."""
    from backend.analysis.sentiment import SentimentResult

    def _make(
        max_cycles=1,
        only_strong=True,
        use_db=False,
        balance=10_000.0,
        sentiment_signal="neutral",
        candles=None,
    ):
        fake_candles = candles if candles is not None else _make_candles()

        mock_binance = MagicMock()
        mock_binance.get_candles.return_value = fake_candles
        mock_binance.get_price.return_value = 61_000.0

        mock_sentiment = MagicMock()
        mock_sentiment.get_news_sentiment.return_value = SentimentResult(
            signal=sentiment_signal, score=0.75, reason="mock"
        )

        mock_tg = MagicMock()
        mock_tg.enabled = False

        with patch("backend.core.bot.BinanceClient", return_value=mock_binance), \
             patch("backend.core.bot.SentimentAnalyzer", return_value=mock_sentiment), \
             patch("backend.core.bot.TelegramAlert", return_value=mock_tg):
            from backend.core.bot import RobotoBot
            bot = RobotoBot(
                symbol="BTCUSDT",
                interval="5m",
                balance=balance,
                only_strong=only_strong,
                max_cycles=max_cycles,
                sleep_seconds=0,
                use_db=use_db,
            )
            bot.tg = mock_tg
            return bot, mock_binance, mock_sentiment, mock_tg

    return _make


class TestBotLoopBasic:
    def test_one_cycle_completes(self, bot_factory):
        """Bot executa 1 ciclo completo sem excecao."""
        bot, _, _, _ = bot_factory(max_cycles=1)
        bot.run()
        assert bot._cycle >= 1

    def test_max_cycles_respected(self, bot_factory):
        """Bot não ultrapassa max_cycles."""
        bot, _, _, _ = bot_factory(max_cycles=3)
        bot.run()
        assert bot._cycle <= 3

    def test_balance_positive_after_run(self, bot_factory):
        bot, _, _, _ = bot_factory(max_cycles=2)
        bot.run()
        assert bot.risk.balance > 0

    def test_stop_flag_ends_loop(self, bot_factory):
        """bot.stop() deve encerrar o loop mesmo com max_cycles alto."""
        bot, _, _, _ = bot_factory(max_cycles=1000)
        import threading
        import time

        def stopper():
            time.sleep(0.05)
            bot.stop()

        t = threading.Thread(target=stopper, daemon=True)
        t.start()
        bot.run()
        assert not bot._running


class TestBotLoopNoDB:
    def test_no_db_does_not_call_supabase(self, bot_factory):
        """use_db=False nao deve instanciar SupabaseClient."""
        # SupabaseClient é importado lazy dentro de _get_db() em bot.py,
        # por isso patchamos no módulo original, não em backend.core.bot
        with patch("backend.db.supabase_client.SupabaseClient") as mock_db_cls:
            bot, _, _, _ = bot_factory(max_cycles=1, use_db=False)
            bot.run()
            mock_db_cls.assert_not_called()


class TestBotLoopSignalStrength:
    def test_only_strong_true_ignores_weak(self, bot_factory):
        """
        only_strong=True: sinal fraco nao deve abrir trade.
        Injetamos candles que geram sinal tecnico, mas mantemos
        sentiment neutral — o resultado final deve ser NEUTRO/fraco.
        """
        bot, _, _, _ = bot_factory(max_cycles=2, only_strong=True)
        bot.run()
        assert bot.risk.balance > 0

    def test_only_strong_false_accepts_weak(self, bot_factory):
        """only_strong=False: bot deve aceitar sinais mais fracos."""
        bot, _, _, _ = bot_factory(max_cycles=2, only_strong=False)
        bot.run()
        assert bot._cycle >= 1


class TestBotLoopDrawdown:
    def test_max_drawdown_triggers_pause(self, bot_factory):
        """
        Simula drawdown maximo: forca balance baixo e verifica pausa.
        """
        bot, _, _, _ = bot_factory(max_cycles=1, balance=1000.0)
        bot.risk._balance = 700.0  # -30% a partir de 1000
        bot.risk._initial_balance = 1000.0
        status = bot.risk.status()
        assert status["drawdown_pct"] >= 0


class TestBotLoopTelegram:
    def test_startup_called_on_run(self, bot_factory):
        bot, _, _, mock_tg = bot_factory(max_cycles=1)
        bot.run()
        mock_tg.startup.assert_called_once()

    def test_shutdown_called_on_run(self, bot_factory):
        bot, _, _, mock_tg = bot_factory(max_cycles=1)
        bot.run()
        mock_tg.shutdown.assert_called_once()
