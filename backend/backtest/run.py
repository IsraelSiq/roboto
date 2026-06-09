"""
Roboto — Backtest Runner

Uso:
    python -m backend.backtest.run
    python -m backend.backtest.run --symbol ETHUSDT --interval 1h --start 2026-01-01
    python -m backend.backtest.run --sentiment neutral --weak
    python -m backend.backtest.run --sentiment negative

SL/TP padrões por timeframe (Risk:Reward 1:2):
    1m  → SL=0.3%  TP=0.6%
    5m  → SL=0.8%  TP=1.6%
    15m → SL=1.5%  TP=3.0%
    1h  → SL=2.5%  TP=5.0%
    4h  → SL=4.0%  TP=8.0%
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

# SL/TP padrão por timeframe (Risk:Reward 1:2)
DEFAULT_RISK = {
    "1m":  (0.3, 0.6),
    "3m":  (0.5, 1.0),
    "5m":  (0.8, 1.6),
    "15m": (1.5, 3.0),
    "30m": (2.0, 4.0),
    "1h":  (2.5, 5.0),
    "2h":  (3.0, 6.0),
    "4h":  (4.0, 8.0),
    "1d":  (5.0, 10.0),
}


def main():
    parser = argparse.ArgumentParser(description="Roboto Backtest")
    parser.add_argument("--symbol",    default="BTCUSDT")
    parser.add_argument("--interval",  default="5m")
    parser.add_argument("--start",     default="2026-01-01")
    parser.add_argument("--end",       default=None)
    parser.add_argument("--balance",   type=float, default=10000.0)
    parser.add_argument("--sl",        type=float, default=None, help="Stop loss % (padrão: auto por timeframe)")
    parser.add_argument("--tp",        type=float, default=None, help="Take profit % (padrão: auto por timeframe)")
    parser.add_argument("--sentiment", default="positive", choices=["neutral", "positive", "negative"])
    parser.add_argument("--weak",      action="store_true", help="Aceitar sinais fracos (only_strong=False)")
    parser.add_argument("--no-save",   action="store_true", help="Não salvar no Supabase")
    args = parser.parse_args()

    # SL/TP: usa override do CLI ou pega o padrão do timeframe
    default_sl, default_tp = DEFAULT_RISK.get(args.interval, (1.0, 2.0))
    sl = args.sl if args.sl is not None else default_sl
    tp = args.tp if args.tp is not None else default_tp

    logging.getLogger().info(
        f"[Config] {args.symbol} {args.interval} | SL={sl}% TP={tp}% | "
        f"sentiment={args.sentiment} | only_strong={not args.weak}"
    )

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
        stop_loss_pct=sl,
        take_profit_pct=tp,
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
