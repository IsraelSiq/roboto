"""
Roboto — Métricas de Performance
Calcula win rate, profit factor, drawdown máximo e Sharpe ratio.

Uso:
    from backend.risk.metrics import PerformanceMetrics
    metrics = PerformanceMetrics(trades)
    print(metrics.summary())
"""

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.risk.manager import Trade

logger = logging.getLogger(__name__)


@dataclass
class MetricsResult:
    """Resultado das métricas de performance."""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0          # % de trades vencedores
    profit_factor: float = 0.0     # lucro total / perda total
    max_drawdown: float = 0.0      # maior queda do pico (%) 
    sharpe_ratio: float = 0.0      # retorno ajustado ao risco
    avg_win_pct: float = 0.0       # PnL médio dos wins
    avg_loss_pct: float = 0.0      # PnL médio dos losses
    total_pnl_pct: float = 0.0     # PnL total acumulado
    approved: bool = False         # True se win_rate >= 65%

    def summary(self) -> str:
        status = "✅ APROVADO" if self.approved else "❌ REPROVADO"
        return (
            f"\n{'='*50}\n"
            f"  Performance {status}\n"
            f"{'='*50}\n"
            f"  Trades     : {self.total_trades} ({self.wins}W / {self.losses}L)\n"
            f"  Win Rate   : {self.win_rate:.1f}% (meta: ≥ 65%)\n"
            f"  Profit F.  : {self.profit_factor:.2f} (meta: > 1.5)\n"
            f"  Drawdown   : {self.max_drawdown:.1f}% (meta: < 20%)\n"
            f"  Sharpe     : {self.sharpe_ratio:.2f} (meta: > 1.0)\n"
            f"  PnL total  : {self.total_pnl_pct:+.2f}%\n"
            f"  Avg Win    : {self.avg_win_pct:+.2f}%\n"
            f"  Avg Loss   : {self.avg_loss_pct:+.2f}%\n"
            f"{'='*50}"
        )


class PerformanceMetrics:
    """
    Calcula métricas de performance a partir de uma lista de trades.

    Args:
        trades: Lista de Trade (fechados)
        risk_free_rate: Taxa livre de risco anual (padrão: 0.05 = 5%)
    """

    META_WIN_RATE = 65.0
    META_PROFIT_FACTOR = 1.5
    META_MAX_DRAWDOWN = 20.0
    META_SHARPE = 1.0

    def __init__(self, trades: list = None, risk_free_rate: float = 0.05):
        self.trades = [t for t in (trades or []) if not t.is_open()]
        self.risk_free_rate = risk_free_rate

    def calculate(self) -> MetricsResult:
        """Calcula todas as métricas e retorna MetricsResult."""
        if not self.trades:
            return MetricsResult()

        pnls = [t.pnl_pct for t in self.trades if t.pnl_pct is not None]
        wins  = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total = len(pnls)
        n_wins = len(wins)
        n_losses = len(losses)

        win_rate = (n_wins / total * 100) if total > 0 else 0.0

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        avg_win  = (sum(wins) / n_wins) if wins else 0.0
        avg_loss = (sum(losses) / n_losses) if losses else 0.0
        total_pnl = sum(pnls)

        max_dd = self._calc_max_drawdown(pnls)
        sharpe = self._calc_sharpe(pnls)

        approved = (
            win_rate >= self.META_WIN_RATE and
            profit_factor >= self.META_PROFIT_FACTOR and
            max_dd < self.META_MAX_DRAWDOWN and
            sharpe >= self.META_SHARPE
        )

        return MetricsResult(
            total_trades=total,
            wins=n_wins,
            losses=n_losses,
            win_rate=round(win_rate, 2),
            profit_factor=round(profit_factor, 4) if profit_factor != float("inf") else 999.0,
            max_drawdown=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 4),
            avg_win_pct=round(avg_win, 4),
            avg_loss_pct=round(avg_loss, 4),
            total_pnl_pct=round(total_pnl, 4),
            approved=approved,
        )

    # ----------------------------------------------------------
    # HELPERS
    # ----------------------------------------------------------

    @staticmethod
    def _calc_max_drawdown(pnls: list[float]) -> float:
        """Calcula o maior drawdown sequencial da curva de equity."""
        if not pnls:
            return 0.0
        equity = 100.0
        peak = equity
        max_dd = 0.0
        for pnl in pnls:
            equity *= (1 + pnl / 100)
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _calc_sharpe(self, pnls: list[float]) -> float:
        """Calcula Sharpe ratio (anualizado, base diária)."""
        if len(pnls) < 2:
            return 0.0
        n = len(pnls)
        mean = sum(pnls) / n
        variance = sum((p - mean) ** 2 for p in pnls) / (n - 1)
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        # Ajuste: assume ~288 candles de 5min por dia
        rf_per_trade = self.risk_free_rate / 288
        return round((mean - rf_per_trade) / std * math.sqrt(n), 4)


# ----------------------------------------------------------
# Teste rápido
# ----------------------------------------------------------
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    from backend.risk.manager import RiskManager, Trade
    from backend.analysis.signals import SignalDecision

    print("\nRoboto — Métricas de Performance Test")
    print("Simulando 20 trades...\n")

    rm = RiskManager(balance=10000.0, only_strong=False)

    # Simula 20 trades com distribuição realista
    import random
    random.seed(42)
    results = []

    for i in range(20):
        price = 60000.0 + random.uniform(-2000, 2000)
        direction = random.choice(["CALL_FORTE", "PUT_FORTE"])
        decision = SignalDecision(
            final=direction,
            technical_signal=direction.split("_")[0],
            sentiment_signal="positive" if direction == "CALL_FORTE" else "negative",
            reason="Simulação",
            confidence=0.90,
            symbol="BTCUSDT",
            timeframe="5m",
            current_price=price,
            rsi=50.0,
            sentiment_score=0.85,
            news_count=5,
        )

        ok, reason = rm.can_trade(decision)
        if not ok:
            # Fora da pausa, simula diretamente
            pass

        trade = Trade(
            id=f"t{i:02d}",
            symbol="BTCUSDT",
            direction=direction.split("_")[0],
            strength="FORTE",
            entry_price=price,
            stop_loss=price * 0.95,
            take_profit=price * 1.10,
            opened_at="2026-01-01T00:00:00Z",
        )

        # 70% win rate simulado
        if random.random() < 0.70:
            exit_price = trade.take_profit
        else:
            exit_price = trade.stop_loss

        rm.close_trade(trade, exit_price)

    metrics = PerformanceMetrics(rm.closed_trades)
    result = metrics.calculate()
    print(result.summary())
