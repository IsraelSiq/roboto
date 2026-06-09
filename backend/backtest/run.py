"""
Roboto — Backtest Runner
Script de entrada para rodar um backtest completo.

Uso:
    python -m backend.backtest.run
    python -m backend.backtest.run --symbol ETHUSDT --interval 1h --start 2026-01-01 --balance 5000
    python -m backend.backtest.run --sentiment positive --weak
"""

import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)

from backend.backtest.data_loader import BacktestDataLoader
from backend.backtest.engine import BacktestEngine
from backend.backtest.report import BacktestReporter


def main():
    parser = argparse.ArgumentParser(description="Roboto Backtest")
    parser.add_argument("--symbol",    default="BTCUSDT")
    parser.add_argument("--interval",  default="5m")
    parser.add_argument("--start",     default="2026-01-01")
    parser.add_argument("--end",       default=None)
    parser.add_argument("--balance",   type=float, default=10000.0)
    parser.add_argument("--sl",        type=float, default=5.0,  help="Stop loss %")
    parser.add_argument("--tp",        type=float, default=10.0, help="Take profit %")
    parser.add_argument("--sentiment", default="neutral", choices=["neutral", "positive", "negative"])
    parser.add_argument("--weak",      action="store_true", help="Aceitar sinais fracos")
    parser.add_argument("--no-save",   action="store_true", help="Não salvar no Supabase")
    args = parser.parse_args()

    # 1. Carrega dados históricos
    loader = BacktestDataLoader()
    df = loader.load(
        symbol=args.symbol,
        interval=args.interval,
        start=args.start,
        end=args.end,
    )

    if df.empty:
        print("❌ Nenhum dado carregado. Verifique o símbolo e as datas.")
        return

    # 2. Roda o backtest
    engine = BacktestEngine(
        symbol=args.symbol,
        interval=args.interval,
        balance=args.balance,
        only_strong=not args.weak,
        stop_loss_pct=args.sl,
        take_profit_pct=args.tp,
        sentiment_mode=args.sentiment,
    )
    result = engine.run(df)
    print(result.summary())

    # 3. Salva no Supabase
    if not args.no_save:
        reporter = BacktestReporter()
        saved = reporter.save(result)
        if saved:
            print("✅ Resultado salvo no Supabase (tabela: backtest_runs)")
        else:
            print("⚠️  Não foi possível salvar no Supabase.")


if __name__ == "__main__":
    main()
