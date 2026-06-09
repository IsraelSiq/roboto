"""
Roboto — Backtest Report
Salva resultados no Supabase e exibe relatório formatado.

Uso:
    reporter = BacktestReporter()
    reporter.save(result)
"""

import logging
from datetime import datetime, timezone

from backend.backtest.engine import BacktestResult

logger = logging.getLogger(__name__)


class BacktestReporter:
    def __init__(self):
        self._db = None

    def _get_db(self):
        if self._db is None:
            try:
                from backend.db.supabase_client import SupabaseClient
                self._db = SupabaseClient()
            except Exception as e:
                logger.warning(f"Supabase indisponível: {e}")
        return self._db

    def save(self, result: BacktestResult, notes: str = "") -> bool:
        """
        Salva o resultado do backtest na tabela backtest_runs do Supabase.

        Returns:
            True se salvo com sucesso, False caso contrário
        """
        db = self._get_db()
        if db is None:
            logger.warning("[Report] Supabase indisponível — resultado não salvo.")
            return False

        try:
            payload = {
                "symbol":           result.symbol,
                "interval":         result.interval,
                "start_date":       result.start_date[:10] if result.start_date else None,
                "end_date":         result.end_date[:10] if result.end_date else None,
                "initial_balance":  result.initial_balance,
                "final_balance":    result.final_balance,
                "total_candles":    result.total_candles,
                "total_signals":    result.total_signals,
                "total_trades":     result.total_trades,
                "wins":             result.wins,
                "losses":           result.losses,
                "win_rate":         result.win_rate,
                "profit_factor":    result.profit_factor,
                "max_drawdown":     result.max_drawdown,
                "sharpe_ratio":     result.sharpe_ratio,
                "total_pnl_pct":    result.total_pnl_pct,
                "approved":         result.approved,
                "notes":            notes,
                "ran_at":           datetime.now(timezone.utc).isoformat(),
            }
            db.client.table("backtest_runs").insert(payload).execute()
            logger.info(f"[Report] Backtest salvo no Supabase.")
            return True
        except Exception as e:
            logger.error(f"[Report] Erro ao salvar backtest: {e}")
            return False
