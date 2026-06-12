import argparse
import json
import logging

from backend.backtest.data_loader import BacktestDataLoader
from backend.backtest.engine import BacktestEngine
from backend.backtest.report import BacktestReporter

"""
Roboto — Backtest Runner

Uso:
    python -m backend.backtest.run
    python -m backend.backtest.run --symbol ETHUSDT --interval 1h --start 2026-01-01
    python -m backend.backtest.run --sentiment neutral --weak
    python -m backend.backtest.run --atr --atr-mult 2.0 --rr 2.5
    python -m backend.backtest.run --macro --macro-tf 4h
    python -m backend.backtest.run --json   # só imprime JSON (para a API)

SL/TP padrões por timeframe (Risk:Reward 1:2):
    1m  → SL=0.3%  TP=0.6%
    5m  → SL=0.8%  TP=1.6%
    15m → SL=1.5%  TP=3.0%
    1h  → SL=2.5%  TP=5.0%
    4h  → SL=4.0%  TP=8.0%
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)

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
    parser.add_argument("--sl",        type=float, default=None,
                        help="Stop loss % (padrão: auto por timeframe)")
    parser.add_argument("--tp",        type=float, default=None,
                        help="Take profit % (padrão: auto por timeframe)")
    parser.add_argument("--sentiment", default="positive",
                        choices=["neutral", "positive", "negative"])
    parser.add_argument("--weak",      action="store_true",
                        help="Aceitar sinais fracos (only_strong=False)")
    # ATR stop (issue #10)
    parser.add_argument("--atr",       action="store_true",
                        help="Usar SL adaptativo por ATR")
    parser.add_argument("--atr-mult",  type=float, default=1.5,
                        help="Multiplicador ATR para SL (padrão: 1.5)")
    parser.add_argument("--rr",        type=float, default=2.0,
                        help="R:R para TP quando --atr ativo (padrão: 2.0)")
    # Macro filter (issue #10)
    parser.add_argument("--macro",     action="store_true",
                        help="Ativar filtro de tendência macro")
    parser.add_argument("--macro-tf",  default="1h",
                        help="Timeframe do filtro macro (padrão: 1h)")
    # Misc
    parser.add_argument("--no-save",   action="store_true",
                        help="Não salvar no Supabase")
    parser.add_argument("--json",      action="store_true",
                        help="Saida apenas em JSON (para integração com API)")
    args = parser.parse_args()

    default_sl, default_tp = DEFAULT_RISK.get(args.interval, (1.0, 2.0))
    sl = args.sl if args.sl is not None else default_sl
    tp = args.tp if args.tp is not None else default_tp

    if not args.json:
        logging.getLogger().info(
            f"[Config] {args.symbol} {args.interval} | SL={sl}% TP={tp}% | "
            f"sentiment={args.sentiment} | only_strong={not args.weak} | "
            f"atr={args.atr} | macro={args.macro}"
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
        if args.json:
            print(json.dumps({"error": "Nenhum dado carregado"}))
        else:
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
        use_atr_stop=args.atr,
        atr_multiplier=args.atr_mult,
        rr_ratio=args.rr,
        macro_filter_enabled=args.macro,
        macro_resample_tf=args.macro_tf,
    )
    result = engine.run(df)

    if args.json:
        # Serialização para a API REST
        trades_data = []
        for t in result.trades:
            trades_data.append({
                "direction":   t.direction,
                "strength":    getattr(t, "strength", None),
                "entry_price": t.entry_price,
                "exit_price":  t.exit_price,
                "stop_loss":   t.stop_loss,
                "take_profit": t.take_profit,
                "pnl_pct":     t.pnl_pct,
                "result":      t.result,
                "opened_at":   str(getattr(t, "opened_at", "")),
                "closed_at":   str(getattr(t, "closed_at", "")),
            })
        equity_data = [{"ts": ts, "equity": eq} for ts, eq in result.equity_curve]
        print(json.dumps({
            "symbol":          result.symbol,
            "interval":        result.interval,
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
            "trades":          trades_data,
            "equity_curve":    equity_data,
        }))
        return

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
