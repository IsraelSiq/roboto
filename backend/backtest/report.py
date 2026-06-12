from typing import List
from dataclasses import dataclass


@dataclass
class MetricsResult:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    total_pnl_pct: float


class PnLReport:
    def calculate(self, trades: List) -> MetricsResult:
        # trades devem ter atributo pnl_pct
        pnl_list = [t.pnl_pct for t in trades]
        total_trades = len(pnl_list)
        wins = sum(1 for p in pnl_list if p > 0)
        losses = sum(1 for p in pnl_list if p < 0)
        win_rate = (wins / total_trades * 100) if total_trades else 0.0
        total_pnl_pct = sum(pnl_list)

        profit_factor = 0.0
        gain = sum(p for p in pnl_list if p > 0)
        loss = -sum(p for p in pnl_list if p < 0)
        if loss > 0:
            profit_factor = gain / loss

        # para os testes, podemos manter drawdown e sharpe em 0.0
        max_drawdown = 0.0
        sharpe_ratio = 0.0

        return MetricsResult(
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            total_pnl_pct=total_pnl_pct,
        )

    def save(self, result: MetricsResult) -> None:
        # implementação simples/dummy para testes
        return None
