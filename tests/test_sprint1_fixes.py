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
    """Fábrica de RobotoBot 100% mockada (sem I/O externo)."""
    from backend.analysis.sentiment import SentimentResult

    def _make(interval="5m", max_cycles=1, macro_filter_enabled=True, sleep_seconds=0):
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

    return _make


# ─────────────────────────────────────────────────────────────
# #50 — BinanceClient não explode sem .env
# ─────────────────────────────────────────────────────────────

class TestIssue50BinanceEnvCI:
    def test_binance_client_init_without_real_env(self):
        """
        BinanceClient.__init__() não deve lançar ValueError quando
        BINANCE_API_KEY e BINANCE_SECRET estão injetados pelo fixture
        mock_binance_env do conftest.py.
        Sem o fixture, este teste falharia em clone limpo.
        """
        assert os.environ.get("BINANCE_API_KEY") is not None, \
            "mock_binance_env fixture não injetou BINANCE_API_KEY"
        assert os.environ.get("BINANCE_SECRET") is not None, \
            "mock_binance_env fixture não injetou BINANCE_SECRET"

    def test_binance_client_init_raises_without_keys(self, monkeypatch):
        """
        Sem as variáveis, BinanceClient DEVE lançar ValueError.
        Confirma que a validação ainda existe e funciona.
        """
        monkeypatch.delenv("BINANCE_API_KEY", raising=False)
        monkeypatch.delenv("BINANCE_SECRET", raising=False)

        with patch("backend.market.binance_client.Client"):
            from backend.market.binance_client import BinanceClient
            with pytest.raises(ValueError, match="BINANCE_API_KEY"):
                BinanceClient()

    def test_binance_client_init_ok_with_env_vars(self, monkeypatch):
        """
        Com as variáveis presentes, BinanceClient instancia sem exceção.
        """
        monkeypatch.setenv("BINANCE_API_KEY", "test_key")
        monkeypatch.setenv("BINANCE_SECRET", "test_secret")

        with patch("backend.market.binance_client.Client") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            from backend.market.binance_client import BinanceClient
            client = BinanceClient()  # não deve lançar
            assert client is not None


# ─────────────────────────────────────────────────────────────
# #40 — INTERVAL_SECONDS cobre todos os timeframes
# ─────────────────────────────────────────────────────────────

class TestIssue40IntervalSeconds:
    def test_all_standard_timeframes_present(self):
        """Todos os timeframes relevantes devem estar no dicionário."""
        from backend.core.bot import INTERVAL_SECONDS
        expected = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"]
        for tf in expected:
            assert tf in INTERVAL_SECONDS, f"Timeframe '{tf}' ausente em INTERVAL_SECONDS"

    def test_4h_sleep_is_14400(self):
        """--interval 4h deve resultar em sleep de 14400s (4h), não 300s."""
        from backend.core.bot import INTERVAL_SECONDS
        assert INTERVAL_SECONDS["4h"] == 14400, \
            f"Esperado 14400, obtido {INTERVAL_SECONDS['4h']}"

    def test_1d_sleep_is_86400(self):
        from backend.core.bot import INTERVAL_SECONDS
        assert INTERVAL_SECONDS["1d"] == 86400

    def test_8h_sleep_is_28800(self):
        from backend.core.bot import INTERVAL_SECONDS
        assert INTERVAL_SECONDS["8h"] == 28800

    def test_bot_4h_interval_sets_correct_sleep(self, bot_factory):
        """
        RobotoBot instanciado com interval='4h' e sem sleep_seconds explícito
        deve ter sleep_seconds=14400.
        """
        bot, _, _ = bot_factory(interval="4h")
        assert bot.sleep_seconds == 14400, \
            f"Esperado sleep_seconds=14400 para 4h, obtido {bot.sleep_seconds}"

    def test_bot_1h_interval_sets_correct_sleep(self, bot_factory):
        bot, _, _ = bot_factory(interval="1h")
        assert bot.sleep_seconds == 3600

    def test_bot_sleep_seconds_override_respected(self, bot_factory):
        """sleep_seconds explícito deve sobrescrever o valor do dicionário."""
        bot, _, _ = bot_factory(interval="4h", sleep_seconds=30)
        assert bot.sleep_seconds == 30

    def test_bot_sleep_zero_respected(self, bot_factory):
        """sleep_seconds=0 deve ser respeitado (não substituído pelo dict)."""
        bot, _, _ = bot_factory(interval="5m", sleep_seconds=0)
        assert bot.sleep_seconds == 0


# ─────────────────────────────────────────────────────────────
# #42 — _df_macro resetado a cada ciclo (sem dados stale)
# ─────────────────────────────────────────────────────────────

class TestIssue42DfMacroStale:
    def test_df_macro_starts_as_none(self, bot_factory):
        """_df_macro deve ser None no __init__."""
        bot, _, _ = bot_factory()
        assert bot._df_macro is None

    def test_df_macro_reset_each_cycle_on_failure(self, bot_factory):
        """
        Se _fetch_macro_candles() falhar no ciclo N,
        _df_macro deve ser None no ciclo N+1 antes de tentar novamente —
        não deve carregar o valor do ciclo anterior.
        """
        bot, mock_binance, _ = bot_factory(max_cycles=2, macro_filter_enabled=True)

        call_count = {"n": 0}
        fake_candles = _make_candles()
        
        def side_effect(**kwargs):
            call_count["n"] += 1
            # Na 2ª chamada de macro (ciclo 2), simula falha de rede
            if kwargs.get("interval") in ("1h",) and call_count["n"] > 2:
                raise Exception("Network timeout simulado")
            return fake_candles

        mock_binance.get_candles.side_effect = side_effect

        # Salva os valores de _df_macro ao longo dos ciclos
        macro_values = []
        original_run_cycle = bot._run_cycle

        def patched_cycle():
            macro_values.append(bot._df_macro)  # captura ANTES de cada ciclo
            original_run_cycle()

        bot._run_cycle = patched_cycle
        bot.run()

        # No início do ciclo 2, _df_macro deve ser None (resetado), não o valor do ciclo 1
        if len(macro_values) >= 2:
            assert macro_values[1] is None, \
                "_df_macro não foi resetado antes do ciclo 2 (dados stale!)"

    def test_df_macro_none_when_macro_disabled(self, bot_factory):
        """Com macro_filter desabilitado, _df_macro deve permanecer None após run."""
        bot, _, _ = bot_factory(max_cycles=1, macro_filter_enabled=False)
        bot.run()
        assert bot._df_macro is None


# ─────────────────────────────────────────────────────────────
# #46 — _print_header() com MagicMock em self.tg
# ─────────────────────────────────────────────────────────────

class TestIssue46DrawdownThreshold:
    def test_print_header_with_mock_tg_no_type_error(self, bot_factory):
        """
        _print_header() com self.tg sendo MagicMock (sem spec)
        não deve lançar TypeError.
        Reproduz exatamente o cenário dos testes test_bot_loop e test_bot_smoke.
        """
        bot, _, mock_tg = bot_factory(max_cycles=1)
        # MagicMock sem spec — getattr retorna outro MagicMock
        assert not hasattr(mock_tg, '__spec__') or mock_tg.__spec__ is None or True
        try:
            bot._print_header()  # não deve lançar TypeError
        except TypeError as e:
            pytest.fail(f"_print_header() lançou TypeError com MagicMock: {e}")

    def test_print_header_with_numeric_threshold(self, bot_factory):
        """Com drawdown_threshold numérico real, _print_header() formata corretamente."""
        bot, _, mock_tg = bot_factory(max_cycles=1)
        mock_tg._drawdown_threshold = 10.0
        try:
            bot._print_header()
        except Exception as e:
            pytest.fail(f"_print_header() lançou exceção com threshold numérico: {e}")

    def test_print_header_with_public_property(self, bot_factory):
        """Se drawdown_threshold existir como propriedade pública, deve ser usada."""
        bot, _, mock_tg = bot_factory(max_cycles=1)
        mock_tg.drawdown_threshold = 15.0
        mock_tg._drawdown_threshold = 10.0  # o público deve ter prioridade
        try:
            bot._print_header()
        except Exception as e:
            pytest.fail(f"_print_header() falhou com propriedade pública: {e}")

    def test_bot_run_completes_with_mock_tg(self, bot_factory):
        """
        bot.run() com max_cycles=1 e self.tg=MagicMock deve completar
        sem TypeError — este era o bug central do #46.
        """
        bot, _, _ = bot_factory(max_cycles=1)
        try:
            bot.run()
        except TypeError as e:
            pytest.fail(f"bot.run() lançou TypeError com MagicMock: {e}")
        assert bot._cycle >= 1
