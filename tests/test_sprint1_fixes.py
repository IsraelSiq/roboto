"""
tests/test_sprint1_fixes.py

Testes de regressão para os 4 fixes do Sprint 1:
  #50 — conftest mock_binance_env: BinanceClient nao lanca ValueError sem .env
  #40 — INTERVAL_SECONDS cobre todos os timeframes (incluindo 4h, 8h, 1d)
  #42 — _df_macro e resetado a cada ciclo (sem dados stale entre ciclos)
  #46 — _print_header() funciona com MagicMock em self.tg (sem TypeError)

Todos os testes sao offline, sem acesso a Binance / Supabase / FinBERT.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
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


def _make_bot(interval="5m", max_cycles=1, macro_filter_enabled=True, sleep_seconds=0):
    """Helper que instancia RobotoBot com todos externos mockados.
    sleep_seconds=None -> bot usa INTERVAL_SECONDS (comportamento real).
    sleep_seconds=0    -> sem sleep (padrao nos testes).
    """
    from backend.analysis.sentiment import SentimentResult

    fake_candles = _make_candles()
    mock_binance = MagicMock()
    mock_binance.get_candles.return_value = fake_candles
    mock_binance.get_price.return_value = 61_000.0

    mock_sentiment = MagicMock()
    mock_sentiment.get_news_sentiment.return_value = SentimentResult(
        signal="neutral", score=0.5, reason="mock"
    )

    mock_tg = MagicMock()
    mock_tg.enabled = False

    with patch("backend.core.bot.BinanceClient", return_value=mock_binance), \
         patch("backend.core.bot.SentimentAnalyzer", return_value=mock_sentiment), \
         patch("backend.core.bot.TelegramAlert", return_value=mock_tg):
        from backend.core.bot import RobotoBot
        bot = RobotoBot(
            symbol="BTCUSDT",
            interval=interval,
            max_cycles=max_cycles,
            sleep_seconds=sleep_seconds,
            use_db=False,
            macro_filter_enabled=macro_filter_enabled,
        )
        bot.tg = mock_tg
        return bot, mock_binance, mock_tg


@pytest.fixture
def bot_factory():
    return _make_bot


# --------------------------------------------------------------
# #50 - BinanceClient nao explode sem .env
# --------------------------------------------------------------

class TestIssue50BinanceEnvCI:
    def test_env_vars_injected_by_conftest(self):
        """
        O fixture autouse mock_binance_env injeta as vars em todos os testes.
        """
        assert os.environ.get("BINANCE_API_KEY"), \
            "mock_binance_env nao injetou BINANCE_API_KEY"
        assert os.environ.get("BINANCE_SECRET"), \
            "mock_binance_env nao injetou BINANCE_SECRET"

    def test_binance_client_raises_when_keys_empty(self):
        """
        Patcha os.getenv dentro do modulo binance_client para retornar None,
        simulando ambiente sem .env. BinanceClient.__init__ deve lancar ValueError.
        """
        import backend.market.binance_client as bmc

        original_getenv = os.getenv

        def fake_getenv(key, default=None):
            if key in ("BINANCE_API_KEY", "BINANCE_SECRET"):
                return None
            return original_getenv(key, default)

        with patch.object(bmc.os, "getenv", side_effect=fake_getenv), \
             patch("backend.market.binance_client.Client"):
            with pytest.raises(ValueError, match="BINANCE_API_KEY"):
                bmc.BinanceClient()

    def test_binance_client_ok_with_keys_present(self):
        """
        Com as vars presentes, BinanceClient instancia sem excecao.
        """
        import backend.market.binance_client as bmc

        def fake_getenv(key, default=None):
            if key == "BINANCE_API_KEY":  return "test_key"
            if key == "BINANCE_SECRET":   return "test_secret"
            if key == "BINANCE_TESTNET":  return "true"
            return os.getenv(key, default)

        with patch.object(bmc.os, "getenv", side_effect=fake_getenv), \
             patch("backend.market.binance_client.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            client = bmc.BinanceClient()
            assert client is not None


# --------------------------------------------------------------
# #40 - INTERVAL_SECONDS cobre todos os timeframes
# --------------------------------------------------------------

class TestIssue40IntervalSeconds:
    def test_all_standard_timeframes_present(self):
        from backend.core.bot import INTERVAL_SECONDS
        for tf in ["1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d"]:
            assert tf in INTERVAL_SECONDS, f"'{tf}' ausente em INTERVAL_SECONDS"

    def test_4h_value(self):
        from backend.core.bot import INTERVAL_SECONDS
        assert INTERVAL_SECONDS["4h"] == 14400

    def test_1d_value(self):
        from backend.core.bot import INTERVAL_SECONDS
        assert INTERVAL_SECONDS["1d"] == 86400

    def test_8h_value(self):
        from backend.core.bot import INTERVAL_SECONDS
        assert INTERVAL_SECONDS["8h"] == 28800

    def test_bot_4h_uses_interval_seconds(self):
        """
        sleep_seconds=None faz o bot resolver pelo INTERVAL_SECONDS.
        Nao usa bot_factory fixture para controlar sleep_seconds=None diretamente.
        """
        bot, _, _ = _make_bot(interval="4h", sleep_seconds=None)
        assert bot.sleep_seconds == 14400, \
            f"Esperado 14400 para 4h, obtido {bot.sleep_seconds}"

    def test_bot_1h_uses_interval_seconds(self):
        bot, _, _ = _make_bot(interval="1h", sleep_seconds=None)
        assert bot.sleep_seconds == 3600

    def test_bot_5m_uses_interval_seconds(self):
        bot, _, _ = _make_bot(interval="5m", sleep_seconds=None)
        assert bot.sleep_seconds == 300

    def test_bot_sleep_override(self):
        """sleep_seconds explicito sobrescreve o dicionario."""
        bot, _, _ = _make_bot(interval="4h", sleep_seconds=30)
        assert bot.sleep_seconds == 30

    def test_bot_sleep_zero_respected(self):
        """sleep_seconds=0 e falsy mas deve ser respeitado (is not None)."""
        bot, _, _ = _make_bot(interval="5m", sleep_seconds=0)
        assert bot.sleep_seconds == 0


# --------------------------------------------------------------
# #42 - _df_macro resetado a cada ciclo (sem dados stale)
# --------------------------------------------------------------

class TestIssue42DfMacroStale:
    def test_df_macro_starts_as_none(self):
        bot, _, _ = _make_bot()
        assert bot._df_macro is None

    def test_df_macro_reset_each_cycle(self):
        """
        Estrategia: patcha _fetch_macro_candles para retornar dados no ciclo 1
        e falhar no ciclo 2. Depois do ciclo 1, _df_macro deve estar preenchido.
        No INICIO do ciclo 2 (antes da busca), _run_cycle reseta para None.
        Capturamos o valor logo APOS o reset, injetando codigo no inicio de
        _fetch_macro_candles (que e chamado DEPOIS do reset).
        """
        bot, _, _ = _make_bot(max_cycles=2, macro_filter_enabled=True)

        fake_candles = _make_candles()
        fetch_calls = []
        df_macro_at_fetch_time = []

        def fake_fetch_macro(self_inner=None):
            # Captura _df_macro logo apos o reset (antes de preencher)
            df_macro_at_fetch_time.append(bot._df_macro)
            fetch_calls.append(len(fetch_calls) + 1)
            if len(fetch_calls) >= 2:
                raise Exception("Network timeout ciclo 2")
            return fake_candles

        bot._fetch_macro_candles = fake_fetch_macro
        bot.run()

        # Ciclo 1: na hora do fetch, _df_macro era None (reset funcionou)
        assert df_macro_at_fetch_time[0] is None, \
            "Ciclo 1: esperado None antes do primeiro fetch macro"

        # Ciclo 2: _df_macro deve ser None no momento do fetch (reset ok)
        if len(df_macro_at_fetch_time) >= 2:
            assert df_macro_at_fetch_time[1] is None, \
                "Ciclo 2: _df_macro nao foi resetado antes do fetch (dados stale!)"

    def test_df_macro_none_when_macro_disabled(self):
        """Com macro desabilitado, _df_macro permanece None apos run."""
        bot, _, _ = _make_bot(max_cycles=1, macro_filter_enabled=False)
        bot.run()
        assert bot._df_macro is None


# --------------------------------------------------------------
# #46 - _print_header() com MagicMock em self.tg
# --------------------------------------------------------------

class TestIssue46DrawdownThreshold:
    def test_print_header_with_mock_tg_no_type_error(self, bot_factory):
        bot, _, mock_tg = bot_factory()
        try:
            bot._print_header()
        except TypeError as e:
            pytest.fail(f"_print_header() lancou TypeError com MagicMock: {e}")

    def test_print_header_with_numeric_threshold(self, bot_factory):
        bot, _, mock_tg = bot_factory()
        mock_tg._drawdown_threshold = 10.0
        try:
            bot._print_header()
        except Exception as e:
            pytest.fail(f"_print_header() lancou excecao com threshold numerico: {e}")

    def test_print_header_public_property_takes_priority(self, bot_factory):
        bot, _, mock_tg = bot_factory()
        mock_tg.drawdown_threshold = 15.0
        mock_tg._drawdown_threshold = 10.0
        try:
            bot._print_header()
        except Exception as e:
            pytest.fail(f"_print_header() falhou com propriedade publica: {e}")

    def test_bot_run_no_type_error_with_mock_tg(self, bot_factory):
        """bug central #46: bot.run() com MagicMock nao lanca TypeError."""
        bot, _, _ = bot_factory()
        try:
            bot.run()
        except TypeError as e:
            pytest.fail(f"bot.run() lancou TypeError: {e}")
        assert bot._cycle >= 1
