# ruff: noqa
"""
tests/test_integration.py
Testes de integração leves — sem conexões reais.
"""
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

from backend.backtest.engine import BacktestEngine


def _make_df(n=200):
    np.random.seed(0)
    close = 60000 + np.cumsum(np.random.randn(n) * 100)
    return pd.DataFrame({
        "open_time": pd.date_range("2024-01-01", periods=n, freq="5min"),
        "open":   close - 50,
        "high":   close + 100,
        "low":    close - 100,
        "close":  close,
        "volume": np.random.uniform(10, 100, n),
    })


class TestBacktestEngineIntegration:
    def test_backtest_roda_sem_excecao(self):
        engine = BacktestEngine(symbol="BTCUSDT", interval="5m", balance=10000.0)
        result = engine.run(_make_df())
        assert result.total_candles == 200
        assert result.final_balance > 0

    def test_backtest_sentiment_mock_expoe_source_backtest_mock(self):
        """_sentiments deve conter objetos com source='backtest_mock'."""
        engine = BacktestEngine()
        # fix #49: atributo correto é _sentiments (plural)
        assert hasattr(engine, "_sentiments"), "BacktestEngine deve ter atributo '_sentiments'"
        for mode in ("positive", "negative", "neutral"):
            assert engine._sentiments[mode].source == "backtest_mock"

    def test_backtest_aprovacao_retorna_bool(self):
        engine = BacktestEngine(symbol="BTCUSDT", interval="5m")
        result = engine.run(_make_df())
        assert isinstance(result.approved, bool)

    def test_backtest_equity_curve_nao_vazia(self):
        engine = BacktestEngine()
        result = engine.run(_make_df())
        assert len(result.equity_curve) > 0
        assert all(bal > 0 for _, bal in result.equity_curve)
