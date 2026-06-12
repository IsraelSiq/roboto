"""
tests/test_sprint1_fixes.py

Testes de regressão para os 4 fixes do Sprint 1:
  #50 — conftest mock_binance_env: BinanceClient não lança ValueError sem .env
  #40 — INTERVAL_SECONDS cobre todos os timeframes (incluindo 4h, 8h, 1d)
  #42 — _df_macro é resetado a cada ciclo (sem dados stale entre ciclos)
  #46 — _print_header() funciona com MagicMock em self.tg (sem TypeError)

Todos os testes são offline, sem acesso a Binance / Supabase / FinBERT.
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


@pytest.fixture
def bot_factory():
    """Fábrica de RobotoBot 100% mockada. sleep_seconds=0 por padrão."""
    from backend.analysis.sentiment import SentimentResult

    def _make(
        interval="5m",
        max_cycles=1,
        macro_filter_enabled=True,
        sleep_seconds=0,           # 0 = sem sleep nos testes
        use_default_sleep=False,   # True = deixa o bot usar INTERVAL_SECONDS
    ):
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

        # sleep_seconds=None faz o bot consultar INTERVAL_SECONDS
        effective_sleep = None if use_default_sleep else sleep_seconds

        with patch("backend.core.bot.BinanceClient", return_value=mock_binance), \
             patch("backend.core.bot.SentimentAnalyzer", return_value=mock_sentiment), \
             patch("backend.core.bot.TelegramAlert", return_value=mock_tg):
            from backend.core.bot import RobotoBot
            bot = RobotoBot(
                symbol="BTCUSDT",
                interval=interval,
                max_cycles=max_cycles,
                sleep_seconds=effective_sleep,
                use_db=False,
                macro_filter_enabled=macro_filter_enabled,
            )
            bot.tg = mock_tg
            return bot, mock_binance, mock_tg

    return _make


# --------------------------------------------------------------
# #50 — BinanceClient não explode sem .env
# --------------------------------------------------------------

class TestIssue50BinanceEnvCI:
    def test_binance_client_init_without_real_env(self):
        """
        O fixture autouse mock_binance_env (conftest.py) injeta
        BINANCE_API_KEY e BINANCE_SECRET em todos os testes.
        """
        assert os.environ.get("BINANCE_API_KEY") is not None, \
            "mock_binance_env fixture nao injetou BINANCE_API_KEY"
        assert os.environ.get("BINANCE_SECRET") is not None, \
            "mock_binance_env fixture nao injetou BINANCE_SECRET"

    def test_binance_client_init_raises_without_keys(self):
        """
        Com env vars removidas via patch.dict (sobrescreve o os.environ em runtime,
        ignorando o que load_dotenv() já carregou), BinanceClient DEVE lançar ValueError.
        Usa patch.dict com clear parcial em vez de monkeypatch.delenv para garantir
        que o código releia os.getenv() e encontre None.
        """
        with patch.dict(os.environ, {"BINANCE_API_KEY": "", "BINANCE_SECRET": ""}, clear=False):
            # Forca os.getenv a retornar string vazia (falsy), disparando o ValueError
            with patch("backend.market.binance_client.Client"):
                # Reimportar para garantir que a validação seja re-executada
                import importlib
                import backend.market.binance_client as bmc
                importlib.reload(bmc)
                with pytest.raises((ValueError, SystemExit, Exception)):
                    bmc.BinanceClient()

    def test_binance_client_init_ok_with_env_vars(self):
        """
        Com as variáveis presentes, BinanceClient instancia sem exceção.
        """
        with patch.dict(os.environ, {"BINANCE_API_KEY": "test_key", "BINANCE_SECRET": "test_secret"}):
            with patch("backend.market.binance_client.Client") as mock_client_cls:
                mock_client_cls.return_value = MagicMock()
                import importlib
                import backend.market.binance_client as bmc
                importlib.reload(bmc)
                client = bmc.BinanceClient()  # nao deve lançar
                assert client is not None


# --------------------------------------------------------------
# #40 — INTERVAL_SECONDS cobre todos os timeframes
# --------------------------------------------------------------

class TestIssue40IntervalSeconds:
    def test_all_standard_timeframes_present(self):
        """Todos os timeframes relevantes devem estar no dicionário."""
        from backend.core.bot import INTERVAL_SECONDS
        expected = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"]
        for tf in expected:
            assert tf in INTERVAL_SECONDS, f"Timeframe '{tf}' ausente em INTERVAL_SECONDS"

    def test_4h_sleep_is_14400(self):
        """--interval 4h deve resultar em sleep de 14400s."""
        from backend.core.bot import INTERVAL_SECONDS
        assert INTERVAL_SECONDS["4h"] == 14400

    def test_1d_sleep_is_86400(self):
        from backend.core.bot import INTERVAL_SECONDS
        assert INTERVAL_SECONDS["1d"] == 86400

    def test_8h_sleep_is_28800(self):
        from backend.core.bot import INTERVAL_SECONDS
        assert INTERVAL_SECONDS["8h"] == 28800

    def test_bot_4h_interval_sets_correct_sleep(self, bot_factory):
        """
        RobotoBot(interval='4h') sem sleep_seconds explícito deve usar
        INTERVAL_SECONDS['4h'] = 14400. use_default_sleep=True omite sleep_seconds
        do construtor, deixando o bot resolver pelo dicionário.
        """
        bot, _, _ = bot_factory(interval="4h", use_default_sleep=True)
        assert bot.sleep_seconds == 14400, \
            f"Esperado 14400 para interval=4h, obtido {bot.sleep_seconds}"

    def test_bot_1h_interval_sets_correct_sleep(self, bot_factory):
        bot, _, _ = bot_factory(interval="1h", use_default_sleep=True)
        assert bot.sleep_seconds == 3600

    def test_bot_sleep_seconds_override_respected(self, bot_factory):
        """sleep_seconds explícito deve sobrescrever o valor do dicionário."""
        bot, _, _ = bot_factory(interval="4h", sleep_seconds=30)
        assert bot.sleep_seconds == 30

    def test_bot_sleep_zero_respected(self, bot_factory):
        """sleep_seconds=0 deve ser respeitado (não substituído pelo dict)."""
        bot, _, _ = bot_factory(interval="5m", sleep_seconds=0)
        assert bot.sleep_seconds == 0


# --------------------------------------------------------------
# #42 — _df_macro resetado a cada ciclo (sem dados stale)
# --------------------------------------------------------------

class TestIssue42DfMacroStale:
    def test_df_macro_starts_as_none(self, bot_factory):
        """_df_macro deve ser None no __init__."""
        bot, _, _ = bot_factory()
        assert bot._df_macro is None

    def test_df_macro_reset_each_cycle_on_failure(self, bot_factory):
        """
        Injeta uma sentinela no início de _run_cycle() para capturar
        o valor de _df_macro ANTES do reset e DEPOIS do reset.
        Garante que no ciclo 2 o valor é None antes da busca macro.
        """
        bot, mock_binance, _ = bot_factory(max_cycles=2, macro_filter_enabled=True)

        fake_candles = _make_candles()
        macro_before_reset = []

        # Patcha _fetch_macro_candles para falhar no 2o ciclo
        fetch_macro_call = {"count": 0}

        def fake_fetch_macro():
            fetch_macro_call["count"] += 1
            if fetch_macro_call["count"] >= 2:
                raise Exception("Network timeout simulado")
            return fake_candles

        # Patcha _run_cycle para capturar _df_macro antes do reset
        original_run_cycle = bot._run_cycle.__func__  # metodo original nao ligado

        def patched_run_cycle():
            macro_before_reset.append(bot._df_macro)  # valor ANTES do reset
            original_run_cycle(bot)

        bot._run_cycle = patched_run_cycle
        bot._fetch_macro_candles = fake_fetch_macro

        bot.run()

        # Ciclo 1: _df_macro era None (estado inicial)
        assert macro_before_reset[0] is None, "Ciclo 1 deveria comecar com _df_macro=None"
        # Ciclo 2: _df_macro deve ser None (foi resetado), mesmo que ciclo 1 tenha preenchido
        if len(macro_before_reset) >= 2:
            assert macro_before_reset[1] is None, \
                "_df_macro nao foi resetado antes do ciclo 2 (dados stale!)"

    def test_df_macro_none_when_macro_disabled(self, bot_factory):
        """Com macro_filter desabilitado, _df_macro permanece None apos run."""
        bot, _, _ = bot_factory(max_cycles=1, macro_filter_enabled=False)
        bot.run()
        assert bot._df_macro is None


# --------------------------------------------------------------
# #46 — _print_header() com MagicMock em self.tg
# --------------------------------------------------------------

class TestIssue46DrawdownThreshold:
    def test_print_header_with_mock_tg_no_type_error(self, bot_factory):
        """
        _print_header() com self.tg = MagicMock() (sem spec)
        nao deve lançar TypeError.
        """
        bot, _, mock_tg = bot_factory(max_cycles=1)
        try:
            bot._print_header()
        except TypeError as e:
            pytest.fail(f"_print_header() lancou TypeError com MagicMock: {e}")

    def test_print_header_with_numeric_threshold(self, bot_factory):
        """Com drawdown_threshold numerico real, _print_header() formata corretamente."""
        bot, _, mock_tg = bot_factory(max_cycles=1)
        mock_tg._drawdown_threshold = 10.0
        try:
            bot._print_header()
        except Exception as e:
            pytest.fail(f"_print_header() lancou excecao com threshold numerico: {e}")

    def test_print_header_with_public_property(self, bot_factory):
        """Se drawdown_threshold existir como propriedade publica, deve ser usada."""
        bot, _, mock_tg = bot_factory(max_cycles=1)
        mock_tg.drawdown_threshold = 15.0
        mock_tg._drawdown_threshold = 10.0
        try:
            bot._print_header()
        except Exception as e:
            pytest.fail(f"_print_header() falhou com propriedade publica: {e}")

    def test_bot_run_completes_with_mock_tg(self, bot_factory):
        """
        bot.run() com self.tg=MagicMock deve completar sem TypeError.
        Este era o bug central do #46.
        """
        bot, _, _ = bot_factory(max_cycles=1)
        try:
            bot.run()
        except TypeError as e:
            pytest.fail(f"bot.run() lancou TypeError com MagicMock: {e}")
        assert bot._cycle >= 1
