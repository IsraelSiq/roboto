"""
tests/test_critical_fixes.py
Testes unitários que cobrem os 3 bugs críticos corrigidos:

    Issue #32 — Trade.__eq__/__hash__ por id evita duplicação em _trades
    Issue #33 — guard None em get_price() antes de check_exit/close_trade
    Issue #34 — MacroFilter None (mercado lateral) bloqueia conservadoramente
"""

from unittest.mock import MagicMock, patch
from dataclasses import replace

import pandas as pd
import pytest

from backend.risk.manager import RiskManager, Trade
from backend.analysis.signals import (
    SignalCombiner,
    SignalDecision,
    CALL_FORTE,
    PUT_FORTE,
    AGUARDAR,
)
from backend.analysis.macro_filter import MacroTrendFilter
from backend.analysis.technical import TechnicalResult
from backend.analysis.sentiment import SentimentResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_decision(final=CALL_FORTE, price=100.0, atr=None):
    d = SignalDecision(
        final=final,
        technical_signal="CALL" if "CALL" in final else ("PUT" if "PUT" in final else "AGUARDAR"),
        sentiment_signal="positive",
        reason="mock",
        confidence=0.9,
        symbol="BTCUSDT",
        timeframe="5m",
        current_price=price,
        rsi=50.0,
        sentiment_score=0.85,
        news_count=5,
    )
    d.atr = atr
    return d


def make_tech(signal="CALL", price=60000.0, atr=None):
    return TechnicalResult(
        signal=signal,
        reason="mock",
        rsi=55.0,
        macd=10.0,
        macd_signal=8.0,
        macd_cross="bullish",
        ema50=59000.0,
        price_vs_ema="above",
        bb_upper=62000.0,
        bb_lower=58000.0,
        current_price=price,
        atr=atr,
    )


def make_sent(signal="positive", score=0.82):
    return SentimentResult(
        signal=signal,
        score=score,
        reason="mock",
        news_count=3,
        source="finbert",
    )


# ---------------------------------------------------------------------------
# Issue #32 — Trade.__eq__/__hash__ por id
# ---------------------------------------------------------------------------

class TestIssue32TradeEquality:
    """Trade com mesmo id deve ser considerado igual, independente do objeto."""

    def test_same_object_is_equal(self):
        rm = RiskManager(balance=10000.0, only_strong=False)
        trade = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0))
        assert trade == trade

    def test_different_object_same_id_is_equal(self):
        rm = RiskManager(balance=10000.0, only_strong=False)
        trade = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0))
        trade_copy = replace(trade)  # novo objeto Python, mesmo id
        assert trade == trade_copy

    def test_different_id_is_not_equal(self):
        rm = RiskManager(balance=10000.0, only_strong=False)
        t1 = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0))
        rm.close_trade(t1, 110.0)
        t2 = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0))
        assert t1 != t2

    def test_hash_same_id(self):
        rm = RiskManager(balance=10000.0, only_strong=False)
        trade = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0))
        trade_copy = replace(trade)
        assert hash(trade) == hash(trade_copy)
        # usável como chave de set
        assert len({trade, trade_copy}) == 1

    def test_close_trade_with_copy_does_not_duplicate(self):
        """close_trade() com objeto diferente (mesmo id) não deve duplicar _trades."""
        rm = RiskManager(balance=10000.0, only_strong=False)
        trade = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0))

        # Simula recebimento de objeto diferente com mesmo id (ex: via API)
        trade_copy = replace(trade)
        assert trade is not trade_copy  # objetos distintos

        rm.close_trade(trade_copy, 110.0)

        # Deve haver exatamente 1 trade na lista, não 2
        assert len(rm._trades) == 1
        assert rm.status()["total_trades"] == 1

    def test_close_trade_normal_flow_no_duplicate(self):
        """Fluxo normal: open + close com mesmo objeto também não duplica."""
        rm = RiskManager(balance=10000.0, only_strong=False)
        trade = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0))
        rm.close_trade(trade, 110.0)
        assert len(rm._trades) == 1
        assert rm.closed_trades[0].result == "WIN"

    def test_trade_not_equal_to_non_trade(self):
        rm = RiskManager(balance=10000.0, only_strong=False)
        trade = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0))
        assert trade != "not-a-trade"
        assert trade != 42
        assert trade != None  # noqa: E711


# ---------------------------------------------------------------------------
# Issue #33 — guard None em get_price()
# ---------------------------------------------------------------------------

class TestIssue33GetPriceNoneGuard:
    """_monitor_open_trade() deve retornar graciosamente quando get_price() == None."""

    def _make_bot_with_open_trade(self, price=100.0):
        """Cria um RobotoBot minimamente configurado com um trade aberto."""
        from backend.core.bot import RobotoBot

        with patch("backend.core.bot.BinanceClient") as MockBinance, \
             patch("backend.core.bot.TechnicalAnalyzer"), \
             patch("backend.core.bot.SentimentAnalyzer"), \
             patch("backend.core.bot.TelegramAlert"):

            MockBinance.return_value = MagicMock()
            bot = RobotoBot(
                symbol="BTCUSDT",
                interval="5m",
                use_db=False,
                only_strong=False,
            )

        # Abre um trade manualmente no RiskManager
        trade = bot.risk.open_trade(make_decision(final=CALL_FORTE, price=price))
        return bot, trade

    def test_none_price_skips_cycle_no_exception(self):
        """get_price() retornando None não deve lançar TypeError."""
        bot, trade = self._make_bot_with_open_trade(price=100.0)
        bot.client.get_price = MagicMock(return_value=None)

        # Não deve levantar nenhuma exceção
        bot._monitor_open_trade()

        # Trade deve continuar aberto — nada foi fechado
        assert bot.risk._open_trade is not None
        assert bot.risk._open_trade.id == trade.id

    def test_none_price_does_not_close_trade(self):
        """Com get_price() == None o trade não é fechado."""
        bot, trade = self._make_bot_with_open_trade(price=100.0)
        bot.client.get_price = MagicMock(return_value=None)
        bot._monitor_open_trade()
        assert len(bot.risk.closed_trades) == 0

    def test_valid_price_at_tp_closes_trade(self):
        """Com preço válido no TP o trade é fechado normalmente."""
        bot, trade = self._make_bot_with_open_trade(price=100.0)
        tp_price = trade.take_profit
        bot.client.get_price = MagicMock(return_value=tp_price)
        bot._monitor_open_trade()
        assert bot.risk._open_trade is None
        assert len(bot.risk.closed_trades) == 1
        assert bot.risk.closed_trades[0].result == "WIN"

    def test_valid_price_at_sl_closes_trade_as_loss(self):
        """Com preço válido no SL o trade é fechado como LOSS."""
        bot, trade = self._make_bot_with_open_trade(price=100.0)
        sl_price = trade.stop_loss
        bot.client.get_price = MagicMock(return_value=sl_price)
        bot._monitor_open_trade()
        assert bot.risk._open_trade is None
        assert bot.risk.closed_trades[0].result == "LOSS"

    def test_exception_in_get_price_skips_cycle(self):
        """Exceção em get_price() (ex: BinanceAPIException) também não derruba o bot."""
        bot, _ = self._make_bot_with_open_trade(price=100.0)
        bot.client.get_price = MagicMock(side_effect=Exception("network error"))
        # Não deve levantar
        bot._monitor_open_trade()
        assert bot.risk._open_trade is not None


# ---------------------------------------------------------------------------
# Issue #34 — MacroFilter None bloqueia mercado lateral
# ---------------------------------------------------------------------------

class TestIssue34MacroFilterNoneBlocks:
    """None retornado pelo MacroFilter deve bloquear o sinal (igual a False)."""

    def _make_df(self, n_rows=70):
        """DataFrame mínimo com coluna 'close' para o MacroFilter."""
        import numpy as np
        prices = 60000.0 + np.random.randn(n_rows) * 500
        return pd.DataFrame({"close": prices})

    def test_false_blocks_signal(self):
        """macro_ok=False deve bloquear e setar macro_blocked=True."""
        macro = MagicMock(spec=MacroTrendFilter)
        macro.tendencia_favoravel = MagicMock(return_value=False)
        macro.enabled = True

        combiner = SignalCombiner(symbol="BTCUSDT", timeframe="5m", macro_filter=macro)
        decision = combiner.combine(
            make_tech(signal="CALL", price=60000.0),
            make_sent(signal="positive"),
            df_macro=self._make_df(),
        )
        assert decision.final == AGUARDAR
        assert decision.macro_blocked is True

    def test_none_blocks_signal_lateral_market(self):
        """macro_ok=None (mercado lateral) deve bloquear — fix #34."""
        macro = MagicMock(spec=MacroTrendFilter)
        macro.tendencia_favoravel = MagicMock(return_value=None)
        macro.enabled = True

        combiner = SignalCombiner(symbol="BTCUSDT", timeframe="5m", macro_filter=macro)
        decision = combiner.combine(
            make_tech(signal="CALL", price=60000.0),
            make_sent(signal="positive"),
            df_macro=self._make_df(),
        )
        assert decision.final == AGUARDAR
        assert decision.macro_blocked is True

    def test_true_allows_signal(self):
        """macro_ok=True deve permitir o sinal normalmente."""
        macro = MagicMock(spec=MacroTrendFilter)
        macro.tendencia_favoravel = MagicMock(return_value=True)
        macro.enabled = True

        combiner = SignalCombiner(symbol="BTCUSDT", timeframe="5m", macro_filter=macro)
        decision = combiner.combine(
            make_tech(signal="CALL", price=60000.0),
            make_sent(signal="positive"),
            df_macro=self._make_df(),
        )
        assert decision.final == CALL_FORTE
        assert decision.macro_blocked is False

    def test_none_blocks_put_lateral(self):
        """macro_ok=None também bloqueia PUT em mercado lateral."""
        macro = MagicMock(spec=MacroTrendFilter)
        macro.tendencia_favoravel = MagicMock(return_value=None)
        macro.enabled = True

        combiner = SignalCombiner(symbol="BTCUSDT", timeframe="5m", macro_filter=macro)
        decision = combiner.combine(
            make_tech(signal="PUT", price=60000.0),
            make_sent(signal="negative", score=0.75),
            df_macro=self._make_df(),
        )
        assert decision.final == AGUARDAR
        assert decision.macro_blocked is True

    def test_aguardar_signal_skips_macro_check(self):
        """Se o sinal combinado já é AGUARDAR, o MacroFilter nem é consultado."""
        macro = MagicMock(spec=MacroTrendFilter)
        macro.tendencia_favoravel = MagicMock(return_value=None)
        macro.enabled = True

        combiner = SignalCombiner(symbol="BTCUSDT", timeframe="5m", macro_filter=macro)
        decision = combiner.combine(
            make_tech(signal="AGUARDAR", price=60000.0),
            make_sent(signal="neutral", score=0.5),
            df_macro=self._make_df(),
        )
        assert decision.final == AGUARDAR
        # MacroFilter não deve ter sido chamado pois o sinal já era AGUARDAR
        macro.tendencia_favoravel.assert_not_called()

    def test_no_macro_filter_allows_signal(self):
        """Sem macro_filter configurado, sinal passa normalmente."""
        combiner = SignalCombiner(symbol="BTCUSDT", timeframe="5m", macro_filter=None)
        decision = combiner.combine(
            make_tech(signal="CALL", price=60000.0),
            make_sent(signal="positive"),
        )
        assert decision.final == CALL_FORTE
        assert decision.macro_blocked is False
