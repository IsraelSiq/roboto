"""
Roboto — Relatório P&L Standalone
Consulta trades fechados do Supabase e exibe métricas de performance.
Funciona sem o bot em execução.

Uso:
    python -m backend.backtest.report
    python -m backend.backtest.report --days 7
    python -m backend.backtest.report --symbol ETHUSDT --days 30
    python -m backend.backtest.report --days 7 --csv relatorio.csv
    python -m backend.backtest.report --all
"""

import argparse
import csv
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


@dataclass
class _FakeTrade:
    """Trade leve recriado a partir dos dados do Supabase para alimentar PerformanceMetrics."""
    id: str
    symbol: str
    direction: str
    entry_price: float
    exit_price: Optional[float]
    pnl_pct: Optional[float]
    result: str
    opened_at: str
    closed_at: Optional[str]

    def is_open(self) -> bool:
        return self.result == "PENDING"

    def pnl_summary(self) -> str:
        if self.pnl_pct is None:
            return "PENDING"
        emoji = "✅" if self.pnl_pct > 0 else "❌"
        return f"{emoji} {self.result} | PnL: {self.pnl_pct:+.2f}%"


class PnLReport:
    """
    Gera relatório de P&L a partir de trades no Supabase.

    Args:
        symbol:   Filtro de par (None = todos)
        days:     Janela de dias para trás (None = todos os registros)
        csv_path: Caminho para exportar CSV (None = sem export)
    """

    def __init__(
        self,
        symbol: Optional[str] = None,
        days: Optional[int] = None,
        csv_path: Optional[str] = None,
    ):
        self.symbol = symbol
        self.days = days
        self.csv_path = csv_path
        self._db = None

    def _get_db(self):
        """Retorna a instância do SupabaseClient, conectando se necessário."""
        if self._db is None:
            try:
                from backend.db.supabase_client import SupabaseClient
                self._db = SupabaseClient()
            except Exception as e:
                print(f"\n❌ Erro ao conectar no Supabase: {e}")
                print("   Verifique SUPABASE_URL e SUPABASE_KEY no .env")
                sys.exit(1)
        return self._db

    def _connect(self):
        self._get_db()

    def run(self):
        """Executa o relatório e imprime no terminal."""
        db = self._get_db()
        trades_raw = self._fetch_trades()

        if not trades_raw:
            print(f"\n⚠️  Nenhum trade encontrado com os filtros aplicados.")
            self._print_filters()
            return

        trades = self._to_fake_trades(trades_raw)
        closed = [t for t in trades if not t.is_open()]

        self._print_header(len(trades_raw), len(closed))
        self._print_trade_list(closed)

        if closed:
            from backend.risk.metrics import PerformanceMetrics
            metrics = PerformanceMetrics(closed)
            result = metrics.calculate()
            print(result.summary())
        else:
            print("\n  Nenhum trade fechado no período.")

        if self.csv_path and closed:
            self._export_csv(closed)

    def save(self, result) -> Optional[dict]:
        """
        Salva resultado de backtest no Supabase.

        Args:
            result: BacktestResult com campos symbol, interval, etc.

        Returns:
            Dict com dados inseridos ou None em caso de erro.
        """
        db = self._get_db()
        payload = {
            "symbol":          result.symbol,
            "timeframe":       result.interval,
            "start_date":      result.start_date,
            "end_date":        result.end_date,
            "initial_balance": result.initial_balance,
            "final_balance":   result.final_balance,
            "total_candles":   result.total_candles,
            "total_signals":   result.total_signals,
            "total_trades":    result.total_trades,
            "wins":            result.wins,
            "losses":          result.losses,
            "win_rate":        result.win_rate,
            "profit_factor":   result.profit_factor,
            "max_drawdown":    result.max_drawdown,
            "sharpe_ratio":    result.sharpe_ratio,
            "total_pnl_pct":   result.total_pnl_pct,
            "approved":        result.approved,
        }
        try:
            table = db.client.table("backtest_results")
            table.insert(payload).execute()
            return payload
        except Exception as e:
            logger.error(f"[BacktestReporter] Erro ao salvar: {e}")
            return None

    # ----------------------------------------------------------
    # BUSCA
    # ----------------------------------------------------------

    def _fetch_trades(self) -> list[dict]:
        """Busca trades do Supabase com filtros de símbolo e período."""
        try:
            db = self._get_db()
            limit = 500 if self.days is None else min(self.days * 50, 1000)
            symbol = self.symbol or "BTCUSDT"
            rows = db.get_trades(symbol=symbol, limit=limit)

            if self.days is not None:
                cutoff = datetime.now(timezone.utc) - timedelta(days=self.days)
                cutoff_str = cutoff.isoformat()
                rows = [
                    r for r in rows
                    if r.get("created_at", "") >= cutoff_str
                ]

            return rows
        except Exception as e:
            logger.error(f"[Report] Erro ao buscar trades: {e}")
            return []

    # ----------------------------------------------------------
    # CONVERSÃO
    # ----------------------------------------------------------

    @staticmethod
    def _to_fake_trades(rows: list[dict]) -> list[_FakeTrade]:
        trades = []
        for r in rows:
            trades.append(_FakeTrade(
                id=str(r.get("id", "?")),
                symbol=r.get("symbol", "?"),
                direction=r.get("direction", "?"),
                entry_price=float(r.get("entry_price") or 0),
                exit_price=float(r["exit_price"]) if r.get("exit_price") is not None else None,
                pnl_pct=float(r["pnl_pct"]) if r.get("pnl_pct") is not None else None,
                result=r.get("result", "PENDING"),
                opened_at=r.get("created_at", ""),
                closed_at=r.get("closed_at"),
            ))
        return trades

    # ----------------------------------------------------------
    # EXIBIÇÃO
    # ----------------------------------------------------------

    def _print_filters(self):
        print(f"  Symbol : {self.symbol or 'todos'}")
        print(f"  Período : {f'últimos {self.days} dias' if self.days else 'todos'}")

    def _print_header(self, total_fetched: int, closed: int):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        period = f"últimos {self.days} dias" if self.days else "todos os registros"
        print("\n" + "═" * 60)
        print(f"  📊 Roboto — Relatório P&L")
        print("═" * 60)
        print(f"  Gerado em  : {now}")
        print(f"  Símbolo    : {self.symbol or 'todos'}")
        print(f"  Período    : {period}")
        print(f"  Registros  : {total_fetched} total | {closed} fechados")
        print("═" * 60)

    def _print_trade_list(self, trades: list[_FakeTrade]):
        if not trades:
            return
        print(f"\n  {'#':<4} {'Par':<10} {'Dir':<6} {'Entry':>12} {'Exit':>12} {'PnL%':>8} {'Result':<8} {'Fechado em'}")
        print(f"  {'-'*4} {'-'*10} {'-'*6} {'-'*12} {'-'*12} {'-'*8} {'-'*8} {'-'*20}")
        for i, t in enumerate(trades, 1):
            entry  = f"${t.entry_price:,.2f}"
            exit_  = f"${t.exit_price:,.2f}" if t.exit_price else "—"
            pnl    = f"{t.pnl_pct:+.2f}%" if t.pnl_pct is not None else "—"
            closed = t.closed_at[:16].replace("T", " ") if t.closed_at else "—"
            emoji  = "✅" if t.result == "WIN" else ("❌" if t.result == "LOSS" else "⏳")
            print(f"  {i:<4} {t.symbol:<10} {t.direction:<6} {entry:>12} {exit_:>12} {pnl:>8} {emoji} {t.result:<7} {closed}")
        print()

    # ----------------------------------------------------------
    # EXPORT CSV
    # ----------------------------------------------------------

    def _export_csv(self, trades: list[_FakeTrade]):
        try:
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "id", "symbol", "direction", "entry_price",
                    "exit_price", "pnl_pct", "result", "opened_at", "closed_at",
                ])
                writer.writeheader()
                for t in trades:
                    writer.writerow({
                        "id":          t.id,
                        "symbol":      t.symbol,
                        "direction":   t.direction,
                        "entry_price": t.entry_price,
                        "exit_price":  t.exit_price or "",
                        "pnl_pct":     t.pnl_pct or "",
                        "result":      t.result,
                        "opened_at":   t.opened_at,
                        "closed_at":   t.closed_at or "",
                    })
            print(f"  📄 CSV exportado: {os.path.abspath(self.csv_path)}")
        except Exception as e:
            print(f"  ❌ Erro ao exportar CSV: {e}")


# Alias para compatibilidade com testes e código que importa BacktestReporter
BacktestReporter = PnLReport


# ----------------------------------------------------------
# Entry point
# ----------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Roboto — Relatório P&L standalone",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--symbol",  default="BTCUSDT", metavar="SYM",
        help="Par de moedas (padrão: BTCUSDT)",
    )
    parser.add_argument(
        "--days",    default=7,  type=int, metavar="N",
        help="Janela de dias para trás (padrão: 7 | 0 = todos)",
    )
    parser.add_argument(
        "--csv",     default=None, metavar="ARQUIVO.csv",
        help="Exporta trades para CSV (ex: --csv relatorio.csv)",
    )
    parser.add_argument(
        "--all",     action="store_true",
        help="Ignora filtro de dias e busca todos os trades",
    )
    args = parser.parse_args()

    report = PnLReport(
        symbol=args.symbol,
        days=None if args.all else (args.days if args.days > 0 else None),
        csv_path=args.csv,
    )
    report.run()
