import logging
from dataclasses import dataclass
from typing import List

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MetricsResult:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    approved: bool

    def summary(self) -> str:
        status = "APROVADO" if self.approved else "REPROVADO"
        return (
            f"Status: {status} | "
            f"Trades: {self.total_trades} | "
            f"Win rate: {self.win_rate:.1f}% | "
            f"PF: {self.profit_factor:.2f} | "
            f"Max DD: {self.max_drawdown:.2f}%"
        )


class PerformanceMetrics:
    """Calcula métricas básicas de performance a partir de uma lista de trades."""

    def __init__(self, trades: List):
        self.trades = [t for t in trades if not t.is_open()]

    def calculate(self) -> MetricsResult:
        if not self.trades:
            return MetricsResult(
                total_trades=0,
                wins=0,
                losses=0,
                win_rate=0.0,
                profit_factor=0.0,
                max_drawdown=0.0,
                approved=False,
            )

        pnl_list = [float(t.pnl_pct or 0.0) for t in self.trades]
        results = [getattr(t, "result", "WIN" if p > 0 else "LOSS") for p, t in zip(pnl_list, self.trades)]

        wins = sum(1 for r in results if r == "WIN")
        losses = sum(1 for r in results if r == "LOSS")
        total = len(results)
        win_rate = (wins / total) * 100.0 if total > 0 else 0.0

        gross_profit = sum(p for p in pnl_list if p > 0)
        gross_loss = -sum(p for p in pnl_list if p < 0)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        equity = 100.0
        curve = []
        for p in pnl_list:
            equity *= 1.0 + p / 100.0
            curve.append(equity)

        equities = np.array(curve, dtype=float)
        peaks = np.maximum.accumulate(equities)
        drawdowns = (peaks - equities) / peaks * 100.0
        max_dd = float(drawdowns.max()) if drawdowns.size > 0 else 0.0

        approved = win_rate >= 60.0 and profit_factor >= 1.5

        return MetricsResult(
            total_trades=total,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=max_dd,
            approved=approved,
        )
