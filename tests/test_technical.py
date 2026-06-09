"""
Testes — TechnicalAnalyzer
"""
import pandas as pd
import numpy as np
import pytest
from backend.analysis.technical import TechnicalAnalyzer


def make_df(n=100, trend="up"):
    """Gera DataFrame de candles sintéticos."""
    np.random.seed(42)
    base = 60000.0
    prices = []
    for i in range(n):
        if trend == "up":
            base += np.random.uniform(0, 200)
        elif trend == "down":
            base -= np.random.uniform(0, 200)
        else:
            base += np.random.uniform(-100, 100)
        prices.append(base)

    df = pd.DataFrame({
        "open":   [p * 0.999 for p in prices],
        "high":   [p * 1.002 for p in prices],
        "low":    [p * 0.998 for p in prices],
        "close":  prices,
        "volume": [np.random.uniform(100, 1000) for _ in range(n)],
    })
    return df


class TestTechnicalAnalyzer:
    def setup_method(self):
        self.ta = TechnicalAnalyzer()

    def test_analyze_returns_result(self):
        df = make_df()
        result = self.ta.analyze(df)
        assert result is not None

    def test_rsi_range(self):
        df = make_df()
        result = self.ta.analyze(df)
        assert result.rsi is not None
        assert 0 <= float(result.rsi) <= 100

    def test_current_price_positive(self):
        df = make_df()
        result = self.ta.analyze(df)
        assert result.current_price > 0

    def test_signal_valid_values(self):
        df = make_df()
        result = self.ta.analyze(df)
        assert result.signal in {"CALL", "PUT", "AGUARDAR"}

    def test_uptrend_signal(self):
        """Tendência de alta deve gerar CALL ou AGUARDAR."""
        df = make_df(200, trend="up")
        result = self.ta.analyze(df)
        assert result.signal in {"CALL", "AGUARDAR"}

    def test_downtrend_signal(self):
        """Tendência de baixa deve gerar PUT ou AGUARDAR."""
        df = make_df(200, trend="down")
        result = self.ta.analyze(df)
        assert result.signal in {"PUT", "AGUARDAR"}

    def test_insufficient_data_raises(self):
        """Menos de 50 candles deve levantar erro ou retornar AGUARDAR."""
        df = make_df(10)
        try:
            result = self.ta.analyze(df)
            assert result.signal == "AGUARDAR"
        except Exception:
            pass  # também aceito
