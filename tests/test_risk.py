"""
tests/test_risk.py
Testes unitários do RiskManager.
"""

from backend.risk.manager import RiskManager
from backend.analysis.signals import SignalDecision, CALL_FORTE, PUT_FORTE, CALL_FRACO, AGUARDAR


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


def test_can_trade_blocks_aguardar():
    rm = RiskManager()
    ok, reason = rm.can_trade(make_decision(final=AGUARDAR))
    assert ok is False
    assert "AGUARDAR" in reason


def test_can_trade_blocks_weak_when_only_strong():
    rm = RiskManager(only_strong=True)
    ok, reason = rm.can_trade(make_decision(final=CALL_FRACO))
    assert ok is False
    assert "Sinal fraco" in reason


def test_open_trade_call_uses_pct_stop_by_default():
    rm = RiskManager(stop_loss_pct=5.0, take_profit_pct=10.0)
    trade = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0))
    assert trade.direction == "CALL"
    assert trade.stop_loss == 95.0
    assert trade.take_profit == 110.0
    assert trade.stop_loss_mode == "pct"
    assert trade.atr_at_entry is None


def test_open_trade_put_uses_pct_stop_by_default():
    rm = RiskManager(stop_loss_pct=5.0, take_profit_pct=10.0)
    trade = rm.open_trade(make_decision(final=PUT_FORTE, price=100.0))
    assert trade.direction == "PUT"
    assert trade.stop_loss == 105.0
    assert trade.take_profit == 90.0
    assert trade.stop_loss_mode == "pct"


def test_open_trade_call_uses_atr_when_enabled():
    # entry=100, ATR=4, mult=2.0 -> risco=8 -> SL=92, TP=100+8*2.0=116
    rm = RiskManager(use_atr_stop=True, atr_multiplier=2.0, rr_ratio=2.0, stop_loss_pct=5.0)
    trade = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0, atr=4.0))
    assert trade.direction == "CALL"
    assert trade.stop_loss == 92.0
    assert trade.take_profit == 116.0
    assert trade.stop_loss_mode == "atr"
    assert trade.atr_at_entry == 4.0


def test_open_trade_put_uses_atr_when_enabled():
    # entry=100, ATR=4, mult=2.0 -> risco=8 -> SL=108, TP=100-8*2.0=84
    rm = RiskManager(use_atr_stop=True, atr_multiplier=2.0, rr_ratio=2.0, stop_loss_pct=5.0)
    trade = rm.open_trade(make_decision(final=PUT_FORTE, price=100.0, atr=4.0))
    assert trade.direction == "PUT"
    assert trade.stop_loss == 108.0
    assert trade.take_profit == 84.0
    assert trade.stop_loss_mode == "atr"
    assert trade.atr_at_entry == 4.0


def test_open_trade_falls_back_to_pct_when_atr_missing():
    rm = RiskManager(use_atr_stop=True, atr_multiplier=2.0, stop_loss_pct=5.0)
    trade = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0, atr=None))
    assert trade.stop_loss == 95.0
    assert trade.stop_loss_mode == "pct"


def test_check_exit_call_tp_and_sl():
    rm = RiskManager(stop_loss_pct=5.0, take_profit_pct=10.0)
    trade = rm.open_trade(make_decision(final=CALL_FORTE, price=100.0))
    assert rm.check_exit(trade, 95.0) == "SL"
    assert rm.check_exit(trade, 110.0) == "TP"


def test_check_exit_put_tp_and_sl():
    rm = RiskManager(stop_loss_pct=5.0, take_profit_pct=10.0)
    trade = rm.open_trade(make_decision(final=PUT_FORTE, price=100.0))
    assert rm.check_exit(trade, 105.0) == "SL"
    assert rm.check_exit(trade, 90.0) == "TP"


def test_close_trade_put_profit_when_price_falls():
    rm = RiskManager(balance=10000.0)
    trade = rm.open_trade(make_decision(final=PUT_FORTE, price=100.0))
    rm.close_trade(trade, 90.0)
    assert trade.result == "WIN"
    assert trade.pnl_pct == 10.0
    assert rm.balance == 11000.0
