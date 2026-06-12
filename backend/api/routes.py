from datetime import datetime

from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from typing import Optional

from backend.api.schemas import BacktestRequest
from backend.backtest.data_loader import BacktestDataLoader
from backend.backtest.engine import BacktestEngine
from backend.backtest.run import DEFAULT_RISK
from backend.backtest.report import PnLReport
from backend.core.bot import RobotoBot, SentimentAnalyzer
from backend.db.supabase_client import SupabaseClient

router = APIRouter()

_API_TOKEN: Optional[str] = None
_bot: Optional[RobotoBot] = None
_bot_thread = None


def _get_db() -> Optional[SupabaseClient]:
    try:
        return SupabaseClient()
    except Exception:
        return None


def _get_sentiment_analyzer() -> SentimentAnalyzer:
    return SentimentAnalyzer()


@router.get("/")
async def root():
    return {"status": "ok", "message": "Roboto API"}


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/warmup")
async def warmup():
    analyzer = _get_sentiment_analyzer()
    if analyzer.is_model_loaded:
        return {"status": "already_loaded", "finbert_loaded": True}
    # força o load do modelo
    analyzer.warmup()
    return {"status": "warming_up", "finbert_loaded": False}


@router.get("/signals")
async def get_signals(symbol: str, limit: int = 10):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    rows = db.get_last_signals(symbol=symbol, limit=limit) or []
    return {"signals": rows}


@router.get("/trades")
async def get_trades():
    if _bot is None or not getattr(_bot, "trades", None):
        return {"total": 0, "trades": []}
    trades = list(_bot.trades)
    return {"total": len(trades), "trades": trades}


@router.get("/trades/history")
async def get_trades_history(symbol: Optional[str] = None):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return db.get_trades(symbol=symbol)


@router.post("/bot/start")
async def bot_start(payload: dict):
    global _bot, _bot_thread

    if _API_TOKEN and payload.get("token") and payload["token"] != _API_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if _bot is not None and getattr(_bot, "_running", False):
        return {"status": "already_running", "symbol": _bot.symbol}

    symbol = payload["symbol"]
    interval = payload["interval"]
    balance = float(payload.get("balance", 10000.0))
    only_strong = bool(payload.get("only_strong", True))

    _bot = RobotoBot(symbol=symbol, interval=interval, balance=balance, only_strong=only_strong)

    import threading

    def _run():
        _bot.run()

    _bot_thread = threading.Thread(target=_run, daemon=True)
    _bot_thread.start()

    return {"status": "started", "symbol": symbol}


@router.post("/bot/stop")
async def bot_stop(authorization: Optional[str] = Depends(lambda: None)):
    global _bot

    if _API_TOKEN:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        token = authorization.split(" ", 1)[1]
        if token != _API_TOKEN:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if _bot is not None:
        _bot.stop()
    return {"status": "stopped"}


@router.get("/metrics")
async def metrics():
    if _bot is None or not getattr(_bot, "trades", None):
        return {"metrics": None}
    report = PnLReport()
    m = report.calculate(_bot.trades)
    return {"metrics": m}


@router.get("/status")
async def status_endpoint():
    analyzer = _get_sentiment_analyzer()
    return {"status": "ok", "finbert_loaded": analyzer.is_model_loaded}


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


app = FastAPI()
app.include_router(router)
