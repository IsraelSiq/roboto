"""
Testes — PerformanceMetrics
"""
import pytest
from unittest.mock import MagicMock
from backend.risk.metrics import PerformanceMetrics, MetricsResult


def make_trade(pnl: float, result: str = None):
    t = MagicMock()
    t.pnl_pct = pnl
    t.result = result or ("WIN" if pnl > 0 else "LOSS")
    t.is_open.return_value = False
    return t


class TestPerformanceMetrics:
    def test_empty_trades(self):
        m = PerformanceMetrics([])
        result = m.calculate()
        assert result.total_trades == 0
        assert result.approved is False

    def test_win_rate_100(self):
        trades = [make_trade(10.0) for _ in range(5)]
        result = PerformanceMetrics(trades).calculate()
        assert result.win_rate == 100.0
        assert result.wins == 5
        assert result.losses == 0

    def test_win_rate_0(self):
        trades = [make_trade(-5.0) for _ in range(5)]
        result = PerformanceMetrics(trades).calculate()
        assert result.win_rate == 0.0

    def test_win_rate_calculation(self):
        trades = [make_trade(10.0)] * 7 + [make_trade(-5.0)] * 3
        result = PerformanceMetrics(trades).calculate()
        assert result.win_rate == 70.0

    def test_profit_factor(self):
        trades = [make_trade(10.0)] * 6 + [make_trade(-5.0)] * 4
        result = PerformanceMetrics(trades).calculate()
        # gross_profit=60, gross_loss=20 => PF=3.0
        assert result.profit_factor == pytest.approx(3.0, rel=0.01)

    def test_approved_good_strategy(self):
        """Estratégia com 70% WR e PF alto deve ser aprovada."""
        trades = [make_trade(10.0)] * 14 + [make_trade(-3.0)] * 6
        result = PerformanceMetrics(trades).calculate()
        assert result.approved is True

    def test_not_approved_bad_strategy(self):
        """Estratégia perdedora não deve ser aprovada."""
        trades = [make_trade(-5.0)] * 8 + [make_trade(2.0)] * 2
        result = PerformanceMetrics(trades).calculate()
        assert result.approved is False

    def test_max_drawdown_positive(self):
        trades = [make_trade(5.0), make_trade(-10.0), make_trade(5.0)]
        result = PerformanceMetrics(trades).calculate()
        assert result.max_drawdown > 0

    def test_summary_contains_status(self):
        trades = [make_trade(10.0)] * 5
        result = PerformanceMetrics(trades).calculate()
        summary = result.summary()
        assert "APROVADO" in summary or "REPROVADO" in summary
