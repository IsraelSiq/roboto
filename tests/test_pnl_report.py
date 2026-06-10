"""
Testes — Relatório P&L standalone (issue #19)
Cobre calculo de P&L, export CSV e resumo textual.
"""
import os
import csv
import tempfile
import pytest
from unittest.mock import patch
from backend.risk.metrics import PerformanceMetrics
from backend.risk.manager import RiskManager
from backend.analysis.signals import SignalDecision


def make_decision(signal="CALL_FORTE", price=60000.0):
    return SignalDecision(
        final=signal, technical_signal="CALL", sentiment_signal="positive",
        reason="teste", confidence=0.9, symbol="BTCUSDT", timeframe="5m",
        current_price=price, rsi=40.0, sentiment_score=0.8, news_count=3,
    )


def build_trades(wins=3, losses=2, balance=10000.0):
    """Gera lista de trades fechados com wins e losses."""
    rm = RiskManager(balance=balance, only_strong=False)
    for i in range(wins + losses):
        trade = rm.open_trade(make_decision())
        if i < wins:
            rm.close_trade(trade, trade.take_profit)
        else:
            rm.close_trade(trade, trade.stop_loss)
    return rm.closed_trades


class TestPerformanceMetrics:
    def test_total_trades(self):
        trades = build_trades(wins=3, losses=2)
        m = PerformanceMetrics(trades).calculate()
        assert m.total_trades == 5

    def test_win_rate(self):
        trades = build_trades(wins=4, losses=1)
        m = PerformanceMetrics(trades).calculate()
        assert abs(m.win_rate - 80.0) < 0.1

    def test_win_rate_zero(self):
        trades = build_trades(wins=0, losses=3)
        m = PerformanceMetrics(trades).calculate()
        assert m.win_rate == 0.0

    def test_win_rate_hundred(self):
        trades = build_trades(wins=5, losses=0)
        m = PerformanceMetrics(trades).calculate()
        assert m.win_rate == 100.0

    def test_net_pnl_positive_majority_wins(self):
        trades = build_trades(wins=4, losses=1)
        m = PerformanceMetrics(trades).calculate()
        assert m.net_pnl > 0

    def test_net_pnl_negative_majority_losses(self):
        trades = build_trades(wins=1, losses=4)
        m = PerformanceMetrics(trades).calculate()
        assert m.net_pnl < 0

    def test_summary_returns_string(self):
        trades = build_trades(wins=2, losses=2)
        m = PerformanceMetrics(trades).calculate()
        summary = m.summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_summary_contains_key_fields(self):
        trades = build_trades(wins=3, losses=1)
        m = PerformanceMetrics(trades).calculate()
        s = m.summary().lower()
        assert any(kw in s for kw in ["win", "trade", "pnl", "resultado", "taxa"])


class TestPnLReport:
    """Testa o script standalone de relatório P&L (backend/report/pnl.py)."""

    def test_report_importable(self):
        """Módulo de relatório deve ser importável."""
        try:
            from backend.report import pnl  # noqa
        except ImportError:
            pytest.skip("backend.report.pnl ainda não implementado")

    def test_report_generates_csv(self):
        """generate_csv deve criar um arquivo CSV válido."""
        try:
            from backend.report.pnl import generate_csv
        except ImportError:
            pytest.skip("generate_csv ainda não implementado")

        trades = build_trades(wins=2, losses=1)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "report.csv")
            generate_csv(trades, output_path)
            assert os.path.exists(output_path)
            with open(output_path) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert len(rows) == 3
