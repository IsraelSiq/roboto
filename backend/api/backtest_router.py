from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.backtest.engine import BacktestEngine
from backend.backtest.run import DEFAULT_RISK
from backend.backtest.data_loader import BacktestDataLoader
from backend.backtest.report import PnLReport

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/recent")
async def get_recent_backtests():
    report = PnLReport()
    trades = report._fetch_trades()
    return {"count": len(trades), "items": trades}


@router.post("/")
async def run_backtest(
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    start: str = "2026-01-01",
    end: str | None = None,
    balance: float = 10000.0,
    sentiment: str = "positive",
    weak: bool = False,
    atr: bool = False,
    atr_mult: float = 1.5,
    rr: float = 2.0,
    macro: bool = False,
    macro_tf: str = "1h",
    no_save: bool = False,
):
    loader = BacktestDataLoader()
    df = loader.load(symbol=symbol, interval=interval, start=start, end=end)

    if df.empty:
        raise HTTPException(status_code=400, detail="Nenhum dado carregado")

    default_sl, default_tp = DEFAULT_RISK.get(interval, (1.0, 2.0))

    engine = BacktestEngine(
        symbol=symbol,
        interval=interval,
        balance=balance,
        only_strong=not weak,
        stop_loss_pct=default_sl,
        take_profit_pct=default_tp,
        sentiment_mode=sentiment,
        use_atr_stop=atr,
        atr_multiplier=atr_mult,
        rr_ratio=rr,
        macro_filter_enabled=macro,
        macro_resample_tf=macro_tf,
    )

    result = engine.run(df)

    if not no_save:
        report = PnLReport()
        report.save(result)

    return {
        "symbol": result.symbol,
        "interval": result.interval,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "initial_balance": result.initial_balance,
        "final_balance": result.final_balance,
        "total_candles": result.total_candles,
        "total_signals": result.total_signals,
        "total_trades": result.total_trades,
        "wins": result.wins,
        "losses": result.losses,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "max_drawdown": result.max_drawdown,
        "sharpe_ratio": result.sharpe_ratio,
        "total_pnl_pct": result.total_pnl_pct,
        "approved": result.approved,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
