"""
Testes — RiskManager
"""
import pytest
from unittest.mock import MagicMock
from backend.risk.manager import RiskManager


def make_decision(signal="CALL_FORTE", confidence=0.85):
    d = MagicMock()
    d.final = signal
    d.confidence = confidence
    d.signal = signal
    return d


class TestRiskManager:
    def setup_method(self):
        self.rm = RiskManager(balance=10000.0, only_strong=True)

    def test_initial_balance(self):
        assert self.rm.balance == 10000.0
        assert self.rm.initial_balance == 10000.0

    def test_can_trade_call_forte(self):
        ok, reason = self.rm.can_trade(make_decision("CALL_FORTE"))
        assert ok is True

    def test_blocks_aguardar(self):
        ok, reason = self.rm.can_trade(make_decision("AGUARDAR"))
        assert ok is False

    def test_blocks_weak_when_only_strong(self):
        ok, reason = self.rm.can_trade(make_decision("CALL_FRACO"))
        assert ok is False

    def test_allows_weak_when_not_only_strong(self):
        rm = RiskManager(balance=10000.0, only_strong=False)
        ok, reason = rm.can_trade(make_decision("CALL_FRACO"))
        assert ok is True

    def test_open_trade_reduces_balance(self):
        decision = make_decision("CALL_FORTE")
        trade = self.rm.open_trade(decision)
        assert trade is not None
        assert trade.entry_price > 0

    def test_close_trade_win(self):
        decision = make_decision("CALL_FORTE")
        trade = self.rm.open_trade(decision)
        tp = trade.take_profit
        self.rm.close_trade(trade, tp)
        assert trade.result == "WIN"
        assert trade.pnl_pct > 0

    def test_close_trade_loss(self):
        decision = make_decision("CALL_FORTE")
        trade = self.rm.open_trade(decision)
        sl = trade.stop_loss
        self.rm.close_trade(trade, sl)
        assert trade.result == "LOSS"
        assert trade.pnl_pct < 0

    def test_drawdown_pause(self):
        """Bot deve pausar ao atingir max drawdown."""
        rm = RiskManager(balance=10000.0, max_drawdown_pct=5.0, only_strong=False)
        for _ in range(10):
            d = make_decision("PUT_FORTE")
            trade = rm.open_trade(d)
            rm.close_trade(trade, trade.stop_loss)  # sempre perde
            if rm.is_paused():
                break
        assert rm.is_paused()

    def test_max_trades_per_day(self):
        """Não deve abrir mais trades que o limite diário."""
        rm = RiskManager(balance=10000.0, max_trades_day=2, only_strong=False)
        for _ in range(2):
            d = make_decision("CALL_FORTE")
            trade = rm.open_trade(d)
            rm.close_trade(trade, trade.take_profit)
        ok, reason = rm.can_trade(make_decision("CALL_FORTE"))
        assert ok is False
