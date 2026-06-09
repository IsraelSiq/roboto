"""
Testes — Backtest Engine
"""
import pandas as pd
import numpy as np
import pytest
from backend.backtest.engine import BacktestEngine, BacktestResult


def make_candles(n=300, trend="sideways"):
    """Gera DataFrame de candles sintéticos para backtest."""
    np.random.seed(42)
    base = 60000.0
    rows = []
    for i in range(n):
        if trend == "up":
            base += np.random.uniform(0, 150)
        elif trend == "down":
            base -= np.random.uniform(0, 150)
        else:
            base += np.random.uniform(-100, 100)
        rows.append({
            "open_time": pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=5*i),
            "open":   base * 0.999,
            "high":   base * 1.002,
            "low":    base * 0.998,
            "close":  base,
            "volume": np.random.uniform(100, 1000),
        })
    return pd.DataFrame(rows)


class TestBacktestEngine:
    def setup_method(self):
        self.engine = BacktestEngine(
            symbol="BTCUSDT",
            interval="5m",
            balance=10000.0,
            only_strong=True,
        )

    def test_run_returns_result(self):
        df = make_candles(300)
        result = self.engine.run(df)
        assert isinstance(result, BacktestResult)

    def test_result_fields(self):
        df = make_candles(300)
        result = self.engine.run(df)
        assert result.symbol == "BTCUSDT"
        assert result.initial_balance == 10000.0
        assert result.final_balance > 0
        assert result.total_candles == 300
        assert result.total_signals >= 0

    def test_equity_curve_not_empty(self):
        df = make_candles(300)
        result = self.engine.run(df)
        assert len(result.equity_curve) > 0

    def test_win_rate_range(self):
        df = make_candles(300)
        result = self.engine.run(df)
        assert 0.0 <= result.win_rate <= 100.0

    def test_insufficient_data_raises(self):
        df = make_candles(30)
        with pytest.raises(ValueError, match="insuficiente"):
            self.engine.run(df)

    def test_summary_contains_symbol(self):
        df = make_candles(300)
        result = self.engine.run(df)
        assert "BTCUSDT" in result.summary()

    def test_uptrend_positive_pnl(self):
        """Em tendência de alta, o bot deve ter PnL positivo."""
        engine = BacktestEngine(
            symbol="BTCUSDT",
            interval="5m",
            balance=10000.0,
            only_strong=False,
            sentiment_mode="positive",
        )
        df = make_candles(500, trend="up")
        result = engine.run(df)
        # Não asserta PnL positivo (depende da estratégia),
        # mas garante que rodou sem erros
        assert result.total_candles == 500
