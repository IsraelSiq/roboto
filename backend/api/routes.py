from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.api.schemas import BacktestRequest
from backend.backtest.data_loader import BacktestDataLoader
from backend.backtest.engine import BacktestEngine
from backend.backtest.run import DEFAULT_RISK
from backend.backtest.report import PnLReport

router = APIRouter()


@router.get("/")
async def root():
    return {"status": "ok", "message": "Roboto API"}


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.post("/backtest")
async def run_backtest(request: BacktestRequest):
    loader = BacktestDataLoader()
    df = loader.load(
        symbol=request.symbol,
        interval=request.interval,
        start=request.start,
        end=request.end,
    )

    if df.empty:
        raise HTTPException(status_code=400, detail="Nenhum dado carregado")

    default_sl, default_tp = DEFAULT_RISK.get(request.interval, (1.0, 2.0))

    engine = BacktestEngine(
        symbol=request.symbol,
        interval=request.interval,
        balance=request.balance,
        only_strong=not request.weak,
        stop_loss_pct=default_sl,
        take_profit_pct=default_tp,
        sentiment_mode=request.sentiment,
        use_atr_stop=request.atr,
        atr_multiplier=request.atr_mult,
        rr_ratio=request.rr,
        macro_filter_enabled=request.macro,
        macro_resample_tf=request.macro_tf,
    )

    result = engine.run(df)

    if not request.no_save:
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
