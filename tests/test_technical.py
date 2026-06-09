"""
tests/test_technical.py
Testes unitários do TechnicalAnalyzer.
"""

import pytest
import pandas as pd
from backend.analysis.technical import TechnicalAnalyzer


def make_df(n=100, start=100.0, step=1.0):
    rows = []
    price = start
    for _ in range(n):
        rows.append({
            "open": price,
            "high": price + 2,
            "low": price - 2,
            "close": price,
            "volume": 1000,
        })
        price += step
    return pd.DataFrame(rows)


def test_insufficient_candles_returns_wait():
    df = make_df(n=10)
    ta = TechnicalAnalyzer(min_candles=60)
    result = ta.analyze(df)
    assert result.signal == "AGUARDAR"
    assert "Candles insuficientes" in result.reason


def test_returns_atr_when_enough_candles():
    df = make_df(n=100)
    ta = TechnicalAnalyzer(min_candles=60, atr_period=14)
    result = ta.analyze(df)
    assert result.atr is not None
    assert result.atr > 0


def test_above_ema_trending_up():
    df = make_df(n=100, start=100.0, step=1.0)
    ta = TechnicalAnalyzer(min_candles=60)
    result = ta.analyze(df)
    assert result.current_price is not None
    assert result.ema50 is not None
    assert result.price_vs_ema in {"ABOVE", "AT", "BELOW"}
