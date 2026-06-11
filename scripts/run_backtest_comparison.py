#!/usr/bin/env python
"""
Roboto — Backtest Comparativo (Issue #10)

Roda 6 cenários sobre BTCUSDT 5m e compara métricas:
    A  Baseline         SL fixo 0.8% / sem PUT / FinBERT mock neutral
    B  + FinBERT        sentiment positive (CALL_FORTE)
    C  + PUT            sentiment alterna positive/negative por período
    D  + ATR SL         ATR x1.5, R:R 2:1
    E  Completo         ATR + filtro macro 1h
    F  Variações ATR    ATR 1.0x, 1.5x, 2.0x (sem macro)

Uso:
    python scripts/run_backtest_comparison.py
    python scripts/run_backtest_comparison.py --start 2026-01-01 --end 2026-06-10
    python scripts/run_backtest_comparison.py --symbol ETHUSDT
    python scripts/run_backtest_comparison.py --quick   # só cenários A-E, sem F

Saída:
    backtest_comparison.csv        Tabela comparativa de métricas
    backtest_equity_<cenario>.csv  Curva de equity por cenário
    backtest_equity_curve.png      Gráfico das curvas de equity
"""

import argparse
import logging
import sys
import os
from pathlib import Path

# Garante que o root do projeto está no path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.WARNING,  # suprime logs verbosos dos sub-módulos
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)

import pandas as pd

from backend.backtest.data_loader import BacktestDataLoader
from backend.backtest.engine import BacktestEngine

# -------------------------------------------------------------------
# Metas mínimas de aceite
# -------------------------------------------------------------------
METAS = {
    "win_rate":      65.0,
    "profit_factor": 1.5,
    "max_drawdown":  20.0,
    "sharpe_ratio":  1.0,
}

# -------------------------------------------------------------------
# Definição dos cenários
# -------------------------------------------------------------------

def build_scenarios(quick: bool = False) -> list[dict]:
    base = [
        {
            "id": "A-Baseline",
            "desc": "SL fixo 0.8% / neutral",
            "kwargs": {
                "sentiment_mode": "neutral",
                "stop_loss_pct": 0.8,
                "take_profit_pct": 1.6,
                "use_atr_stop": False,
                "macro_filter_enabled": False,
            },
        },
        {
            "id": "B-FinBERT",
            "desc": "sentiment positive",
            "kwargs": {
                "sentiment_mode": "positive",
                "stop_loss_pct": 0.8,
                "take_profit_pct": 1.6,
                "use_atr_stop": False,
                "macro_filter_enabled": False,
            },
        },
        {
            "id": "C-+PUT",
            "desc": "positive + semântica PUT (neutral)",
            "kwargs": {
                "sentiment_mode": "neutral",
                "stop_loss_pct": 0.8,
                "take_profit_pct": 1.6,
                "use_atr_stop": False,
                "macro_filter_enabled": False,
            },
        },
        {
            "id": "D-+ATR",
            "desc": "ATR x1.5 / R:R 2:1",
            "kwargs": {
                "sentiment_mode": "positive",
                "use_atr_stop": True,
                "atr_multiplier": 1.5,
                "rr_ratio": 2.0,
                "macro_filter_enabled": False,
            },
        },
        {
            "id": "E-Completo",
            "desc": "ATR x1.5 + Macro 1h",
            "kwargs": {
                "sentiment_mode": "positive",
                "use_atr_stop": True,
                "atr_multiplier": 1.5,
                "rr_ratio": 2.0,
                "macro_filter_enabled": True,
            },
        },
    ]

    if not quick:
        for mult in [1.0, 1.5, 2.0]:
            base.append({
                "id": f"F-ATR{int(mult*10):02d}",
                "desc": f"ATR x{mult} / R:R 2:1 / sem macro",
                "kwargs": {
                    "sentiment_mode": "positive",
                    "use_atr_stop": True,
                    "atr_multiplier": mult,
                    "rr_ratio": 2.0,
                    "macro_filter_enabled": False,
                },
            })

    return base


# -------------------------------------------------------------------
# Runner
# -------------------------------------------------------------------

def run_scenario(
    scenario: dict,
    df: pd.DataFrame,
    symbol: str,
    interval: str,
    balance: float,
) -> dict:
    print(f"  ► {scenario['id']:15s} {scenario['desc']}...", end=" ", flush=True)
    try:
        engine = BacktestEngine(
            symbol=symbol,
            interval=interval,
            balance=balance,
            only_strong=True,
            **scenario["kwargs"],
        )
        result = engine.run(df)
        row = {
            "Cenário":        scenario["id"],
            "Descrição":      scenario["desc"],
            "Trades":         result.total_trades,
            "Win%":           round(result.win_rate, 1),
            "PF":             round(result.profit_factor, 2),
            "DD%":            round(result.max_drawdown, 1),
            "Sharpe":         round(result.sharpe_ratio, 2),
            "PnL%":           round(result.total_pnl_pct, 2),
            "Saldo Final":    round(result.final_balance, 2),
            "Aprovado":       "✅" if result.approved else "❌",
            "_equity_curve":  result.equity_curve,
        }
        status = "✅" if result.approved else "❌"
        print(f"{status}  Win={result.win_rate:.0f}% PF={result.profit_factor:.2f} DD={result.max_drawdown:.0f}% PnL={result.total_pnl_pct:+.1f}%")
        return row
    except Exception as e:
        print(f"⚠️  ERRO: {e}")
        return {
            "Cenário":    scenario["id"],
            "Descrição":  scenario["desc"],
            "Trades": 0, "Win%": 0, "PF": 0, "DD%": 0,
            "Sharpe": 0, "PnL%": 0, "Saldo Final": balance,
            "Aprovado": "⚠️",
            "_equity_curve": [],
        }


def print_table(rows: list[dict], periodo: str):
    df = pd.DataFrame(rows).drop(columns=["_equity_curve"])
    print(f"\n{'='*80}")
    print(f"  Tabela Comparativa — {periodo}")
    print(f"{'='*80}")
    print(df.to_string(index=False))
    print()
    # Destaca metas
    print(f"  Metas mínimas: Win% >= {METAS['win_rate']} | PF >= {METAS['profit_factor']} | "
          f"DD% <= {METAS['max_drawdown']} | Sharpe >= {METAS['sharpe_ratio']}")
    print(f"{'='*80}\n")


def save_csv(rows: list[dict], filename: str):
    df = pd.DataFrame(rows).drop(columns=["_equity_curve"])
    df.to_csv(filename, index=False)
    print(f"  💾 CSV salvo: {filename}")


def save_equity_csvs(rows: list[dict]):
    for row in rows:
        curve = row.get("_equity_curve", [])
        if not curve:
            continue
        fname = f"backtest_equity_{row['Cenário'].replace(' ', '_')}.csv"
        pd.DataFrame(curve, columns=["timestamp", "balance"]).to_csv(fname, index=False)
    print(f"  💾 Equity CSVs salvos ({len(rows)} arquivos)")


def plot_equity_curves(rows: list[dict], output: str = "backtest_equity_curve.png"):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        fig, ax = plt.subplots(figsize=(14, 6))
        fig.patch.set_facecolor("#0d1117")
        ax.set_facecolor("#161b22")

        colors = ["#58a6ff", "#3fb950", "#f78166", "#e3b341", "#bc8cff", "#79c0ff", "#ffa657", "#ff7b72"]

        for idx, row in enumerate(rows):
            curve = row.get("_equity_curve", [])
            if not curve:
                continue
            timestamps = [pd.Timestamp(ts) for ts, _ in curve]
            balances = [bal for _, bal in curve]
            color = colors[idx % len(colors)]
            lw = 2.5 if row["Cenário"] == "E-Completo" else 1.2
            alpha = 1.0 if row["Cenário"] == "E-Completo" else 0.75
            ax.plot(timestamps, balances, label=f"{row['Cenário']} ({row['PnL%']:+.1f}%)",
                    color=color, linewidth=lw, alpha=alpha)

        ax.set_title("Equity Curve por Cenário — Backtest Comparativo", color="white", fontsize=13, pad=12)
        ax.set_xlabel("Data", color="#8b949e")
        ax.set_ylabel("Saldo (USDT)", color="#8b949e")
        ax.tick_params(colors="#8b949e")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        plt.xticks(rotation=30)
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")
        ax.legend(facecolor="#161b22", labelcolor="white", fontsize=9, loc="upper left")
        ax.grid(axis="y", color="#21262d", linewidth=0.8)

        plt.tight_layout()
        plt.savefig(output, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  📈 Gráfico salvo: {output}")
    except ImportError:
        print("  ⚠️  matplotlib não instalado — gráfico não gerado. Instale com: pip install matplotlib")


def identify_winner(rows: list[dict]) -> str:
    """Retorna o ID do melhor cenário (aprovado com maior PnL%)."""
    approved = [r for r in rows if r["Aprovado"] == "✅"]
    if not approved:
        # Se nenhum aprovado, retorna o de menor drawdown
        return min(rows, key=lambda r: r["DD%"])["Cenário"]
    return max(approved, key=lambda r: r["PnL%"])["Cenário"]


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Backtest comparativo A-E")
    parser.add_argument("--symbol",   default="BTCUSDT")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--start",    default="2026-01-01", help="Início do período in-sample")
    parser.add_argument("--split",    default="2026-05-01", help="Início do período out-of-sample")
    parser.add_argument("--end",      default="2026-06-10", help="Fim do período out-of-sample")
    parser.add_argument("--balance",  default=10000.0, type=float)
    parser.add_argument("--quick",    action="store_true", help="Só cenários A-E, sem variações F")
    parser.add_argument("--no-plot",  action="store_true", help="Não gerar gráfico")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  🤖 Roboto — Backtest Comparativo (Issue #10)")
    print(f"  Símbolo  : {args.symbol} {args.interval}")
    print(f"  In-sample: {args.start} → {args.split}")
    print(f"  Out-sample: {args.split} → {args.end}")
    print("="*60)

    loader = BacktestDataLoader()

    print("\n[1/4] Baixando dados in-sample...")
    df_in = loader.load(symbol=args.symbol, interval=args.interval, start=args.start, end=args.split)
    if df_in.empty:
        print("❌ Sem dados in-sample. Abortando.")
        sys.exit(1)
    print(f"      {len(df_in):,} candles carregados")

    print("\n[2/4] Baixando dados out-of-sample...")
    df_out = loader.load(symbol=args.symbol, interval=args.interval, start=args.split, end=args.end)
    if df_out.empty:
        print("⚠️  Sem dados out-of-sample. Usando só in-sample.")
        df_out = df_in.copy()
    else:
        print(f"      {len(df_out):,} candles carregados")

    scenarios = build_scenarios(quick=args.quick)

    # --- IN-SAMPLE ---
    print("\n[3/4] Rodando cenários (in-sample)...")
    rows_in = []
    for sc in scenarios:
        row = run_scenario(sc, df_in, args.symbol, args.interval, args.balance)
        rows_in.append(row)

    print_table(rows_in, f"In-sample ({args.start} → {args.split})")
    save_csv(rows_in, "backtest_comparison_in_sample.csv")
    save_equity_csvs(rows_in)
    if not args.no_plot:
        plot_equity_curves(rows_in, "backtest_equity_curve_in_sample.png")

    # --- OUT-OF-SAMPLE ---
    print("\n[4/4] Rodando cenários (out-of-sample)...")
    rows_out = []
    for sc in scenarios:
        row = run_scenario(sc, df_out, args.symbol, args.interval, args.balance)
        rows_out.append(row)

    print_table(rows_out, f"Out-of-sample ({args.split} → {args.end})")
    save_csv(rows_out, "backtest_comparison_out_sample.csv")
    if not args.no_plot:
        plot_equity_curves(rows_out, "backtest_equity_curve_out_sample.png")

    # --- VENCEDOR ---
    winner = identify_winner(rows_out)
    print(f"  🏆 Cenário vencedor (out-of-sample): {winner}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
