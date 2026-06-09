"""
Testes — RiskManager
"""
import pytest
from backend.risk.manager import RiskManager
from backend.analysis.signals import SignalDecision


def make_decision(signal="CALL_FORTE", price=61000.0):
    """Cria um SignalDecision real para testar o RiskManager."""
    return SignalDecision(
        final=signal,
        technical_signal="CALL" if "CALL" in signal else "PUT" if "PUT" in signal else "AGUARDAR",
        sentiment_signal="positive",
        reason="teste unitário",
        confidence=0.85,
        symbol="BTCUSDT",
        timeframe="5m",
        current_price=price,
        rsi=45.0,
        sentiment_score=0.85,
        news_count=5,
    )


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
        assert "AGUARDAR" in reason

    def test_blocks_weak_when_only_strong(self):
        ok, reason = self.rm.can_trade(make_decision("CALL_FRACO"))
        assert ok is False
        assert "fraco" in reason.lower() or "only_strong" in reason.lower()

    def test_allows_weak_when_not_only_strong(self):
        rm = RiskManager(balance=10000.0, only_strong=False)
        ok, reason = rm.can_trade(make_decision("CALL_FRACO"))
        assert ok is True

    def test_open_trade_returns_trade(self):
        decision = make_decision("CALL_FORTE")
        trade = self.rm.open_trade(decision)
        assert trade is not None
        assert trade.entry_price == 61000.0
        assert trade.direction == "CALL"
        assert trade.stop_loss < trade.entry_price
        assert trade.take_profit > trade.entry_price

    def test_close_trade_win(self):
        trade = self.rm.open_trade(make_decision("CALL_FORTE"))
        self.rm.close_trade(trade, trade.take_profit)
        assert trade.result == "WIN"
        assert trade.pnl_pct > 0

    def test_close_trade_loss(self):
        trade = self.rm.open_trade(make_decision("CALL_FORTE"))
        self.rm.close_trade(trade, trade.stop_loss)
        assert trade.result == "LOSS"
        assert trade.pnl_pct < 0

    def test_balance_increases_on_win(self):
        trade = self.rm.open_trade(make_decision("CALL_FORTE"))
        self.rm.close_trade(trade, trade.take_profit)
        assert self.rm.balance > 10000.0

    def test_balance_decreases_on_loss(self):
        trade = self.rm.open_trade(make_decision("CALL_FORTE"))
        self.rm.close_trade(trade, trade.stop_loss)
        assert self.rm.balance < 10000.0

    def test_drawdown_pause(self):
        """Bot deve pausar ao atingir max drawdown."""
        rm = RiskManager(balance=10000.0, max_drawdown_pct=5.0, only_strong=False)
        for _ in range(15):
            if rm.is_paused():
                break
            ok, _ = rm.can_trade(make_decision("PUT_FORTE"))
            if not ok:
                break
            trade = rm.open_trade(make_decision("PUT_FORTE"))
            rm.close_trade(trade, trade.stop_loss)
        assert rm.is_paused()

    def test_max_trades_per_day(self):
        """Não deve abrir mais trades que o limite diário."""
        rm = RiskManager(balance=10000.0, max_trades_day=2, only_strong=False)
        for _ in range(2):
            trade = rm.open_trade(make_decision("CALL_FORTE"))
            rm.close_trade(trade, trade.take_profit)
        ok, reason = rm.can_trade(make_decision("CALL_FORTE"))
        assert ok is False
        assert "limite" in reason.lower() or "max" in reason.lower()

    def test_blocks_when_trade_open(self):
        """Não pode abrir segundo trade enquanto tem um aberto."""
        self.rm.open_trade(make_decision("CALL_FORTE"))
        ok, reason = self.rm.can_trade(make_decision("CALL_FORTE"))
        assert ok is False
