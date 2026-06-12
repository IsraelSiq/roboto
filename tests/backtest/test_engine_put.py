"""
tests/backtest/test_engine_put.py
Testes do BacktestEngine para sinais PUT.
"""
import pytest
import pandas as pd
import numpy as np

from backend.backtest.engine import BacktestEngine


def _make_df(n=200, seed=7):
    np.random.seed(seed)
    close = 60000 + np.cumsum(np.random.randn(n) * 100)
    return pd.DataFrame({
        "open_time": pd.date_range("2024-01-01", periods=n, freq="5min"),
        "open":   close - 50,
        "high":   close + 100,
        "low":    close - 100,
        "close":  close,
        "volume": np.random.uniform(10, 100, n),
    })


def test_backtest_engine_aceita_sentiment_negative():
    """Engine com sentiment_mode='negative' deve rodar sem erro."""
    engine = BacktestEngine(sentiment_mode="negative")
    # fix #49: atributo correto é _sentiments (plural)
    assert "negative" in engine._sentiments
    assert engine._sentiments["negative"].signal == "negative"
    result = engine.run(_make_df())
    assert result.total_candles == 200


def test_backtest_engine_modo_both_alterna_sinais():
    """Modo 'both' deve alternar entre positive e negative."""
    engine = BacktestEngine(sentiment_mode="both")
    s1 = engine._get_sentiment()
    s2 = engine._get_sentiment()
    assert s1.signal != s2.signal


def test_backtest_engine_sentiment_neutral_gera_resultado():
    engine = BacktestEngine(sentiment_mode="neutral", only_strong=False)
    result = engine.run(_make_df())
    assert result.total_candles == 200
    assert result.final_balance > 0
