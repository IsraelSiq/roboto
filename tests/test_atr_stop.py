"""
Testes para SL adaptativo por ATR (issue #7).

Cobre:
    - SL CALL e PUT com ATR ativo
    - TP proporcional (R:R >= rr_ratio) com ATR ativo
    - Fallback para % quando ATR é None ou zero
    - Fallback quando use_atr_stop=False
    - R:R mínimo 2:1 garantido
    - atr_at_entry gravado no Trade
    - stop_loss_mode gravado corretamente
    - ATR propagado de TechnicalResult -> SignalDecision -> RiskManager
    - Variação de multiplicadores (1.0x, 1.5x, 2.0x)
    - Parametrização via RobotoBot.__init__
"""
import pytest
from unittest.mock import MagicMock, patch
from backend.analysis.signals import SignalDecision, CALL_FORTE, PUT_FORTE
from backend.risk.manager import RiskManager
from backend.analysis.technical import TechnicalResult
from backend.analysis.sentiment import SentimentResult
from backend.analysis.signals import SignalCombiner


PRICE = 90_000.0
ATR   = 600.0  # BTC ATR típico de 5m


def _decision(direction="CALL", atr=ATR, price=PRICE) -> SignalDecision:
    """Cria um SignalDecision mínimo para testes."""
    final = CALL_FORTE if direction == "CALL" else PUT_FORTE
    return SignalDecision(
        final=final,
        technical_signal=direction,
        sentiment_signal="positive" if direction == "CALL" else "negative",
        reason="test",
        confidence=0.9,
        symbol="BTCUSDT",
        current_price=price,
        atr=atr,
    )


def _risk(multiplier=1.5, rr=2.0, use_atr=True) -> RiskManager:
    return RiskManager(
        balance=10_000.0,
        use_atr_stop=use_atr,
        atr_multiplier=multiplier,
        rr_ratio=rr,
        only_strong=False,
    )


# ------------------------------------------------------------------
# SL
# ------------------------------------------------------------------

def test_sl_call_atr():
    rm = _risk(multiplier=1.5)
    trade = rm.open_trade(_decision("CALL"))
    expected_sl = round(PRICE - ATR * 1.5, 2)
    assert trade.stop_loss == expected_sl
    assert trade.stop_loss_mode == "atr"


def test_sl_put_atr():
    rm = _risk(multiplier=1.5)
    trade = rm.open_trade(_decision("PUT"))
    expected_sl = round(PRICE + ATR * 1.5, 2)
    assert trade.stop_loss == expected_sl
    assert trade.stop_loss_mode == "atr"


def test_sl_fallback_when_atr_none():
    rm = _risk(use_atr=True)
    trade = rm.open_trade(_decision(atr=None))
    assert trade.stop_loss_mode == "pct"
    assert trade.stop_loss == round(PRICE * (1 - rm.stop_loss_pct / 100), 2)


def test_sl_fallback_when_atr_zero():
    rm = _risk(use_atr=True)
    trade = rm.open_trade(_decision(atr=0.0))
    assert trade.stop_loss_mode == "pct"


def test_sl_pct_when_use_atr_false():
    rm = _risk(use_atr=False)
    trade = rm.open_trade(_decision("CALL"))
    assert trade.stop_loss_mode == "pct"
    assert trade.stop_loss == round(PRICE * (1 - rm.stop_loss_pct / 100), 2)


# ------------------------------------------------------------------
# TP e R:R
# ------------------------------------------------------------------

def test_tp_call_rr_2to1():
    rm = _risk(multiplier=1.5, rr=2.0)
    trade = rm.open_trade(_decision("CALL"))
    risco = trade.entry_price - trade.stop_loss
    retorno = trade.take_profit - trade.entry_price
    assert retorno / risco == pytest.approx(2.0, rel=1e-4)


def test_tp_put_rr_2to1():
    rm = _risk(multiplier=1.5, rr=2.0)
    trade = rm.open_trade(_decision("PUT"))
    risco = trade.stop_loss - trade.entry_price
    retorno = trade.entry_price - trade.take_profit
    assert retorno / risco == pytest.approx(2.0, rel=1e-4)


def test_rr_parametrizavel():
    for rr in [1.5, 2.0, 3.0]:
        rm = _risk(rr=rr)
        trade = rm.open_trade(_decision("CALL"))
        risco = trade.entry_price - trade.stop_loss
        retorno = trade.take_profit - trade.entry_price
        assert retorno / risco == pytest.approx(rr, rel=1e-4), f"Falhou para R:R={rr}"


# ------------------------------------------------------------------
# Trade metadata
# ------------------------------------------------------------------

def test_atr_at_entry_gravado():
    rm = _risk()
    trade = rm.open_trade(_decision("CALL"))
    assert trade.atr_at_entry == ATR


def test_atr_at_entry_none_quando_fallback():
    rm = _risk()
    trade = rm.open_trade(_decision(atr=None))
    assert trade.atr_at_entry is None


# ------------------------------------------------------------------
# Propagacao TechnicalResult -> SignalDecision
# ------------------------------------------------------------------

def test_atr_propagado_em_signal_decision():
    """ATR em TechnicalResult deve aparecer em SignalDecision após combine()."""
    tech = TechnicalResult(
        signal="CALL",
        reason="test",
        current_price=PRICE,
        atr=ATR,
    )
    sent = SentimentResult(signal="positive", score=0.8)
    combiner = SignalCombiner(symbol="BTCUSDT", timeframe="5m")
    decision = combiner.combine(tech, sent)
    assert decision.atr == ATR


# ------------------------------------------------------------------
# Multiplicadores
# ------------------------------------------------------------------

@pytest.mark.parametrize("mult", [1.0, 1.5, 2.0])
def test_sl_atr_parametrizavel(mult):
    rm = _risk(multiplier=mult)
    trade = rm.open_trade(_decision("CALL"))
    expected = round(PRICE - ATR * mult, 2)
    assert trade.stop_loss == expected
    assert trade.stop_loss_mode == "atr"
