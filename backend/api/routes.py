"""
Roboto — FastAPI REST
Expõe endpoints para o dashboard e integração com Supabase.

Endpoints:
    GET  /                      — health check (legado)
    GET  /health                — liveness probe (#30)
    GET  /metrics/health        — status detalhado de todas as deps (#31)
    GET  /status                — status do bot
    GET  /signal                — último sinal
    GET  /signals               — histórico de sinais
    GET  /trades                — trades da sessão
    GET  /trades/history        — histórico de trades
    GET  /sessions              — histórico de sessões
    GET  /metrics               — métricas de performance
    GET  /candles               — candles do símbolo
    GET  /price                 — preço atual
    GET  /warmup                — pré-aquece FinBERT
    GET  /reports/summary       — resumo geral (#29)
    GET  /reports/trades        — histórico paginado (#29)
    GET  /reports/export/csv    — exporta CSV (#29)
    GET  /reports/equity-curve  — equity curve (#29)
    POST /bot/start             — inicia bot [Bearer token]
    POST /bot/stop              — para bot  [Bearer token]
    POST /bot/resume            — retoma bot [Bearer token]
    POST /backtest/run          — roda backtest offline (#2)
    GET  /backtest/history      — histórico de backtest runs (#2)
"""

import csv
import io
import logging
import os
import threading
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.core.bot import RobotoBot
from backend.market.binance_client import BinanceClient
from backend.api.backtest_router import router as backtest_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Roboto API",
    description="API do bot de trading Roboto",
    version="1.0.0",
)

# ----------------------------------------------------------
# LOG ESTRUTURADO JSON (#31)
# LOG_FORMAT=json no .env ativa JSON logging
# ----------------------------------------------------------

if os.getenv("LOG_FORMAT", "").lower() == "json":
    import json
    import time as _time

    class _JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            log = {
                "ts":      datetime.utcfromtimestamp(record.created).isoformat() + "Z",
                "level":   record.levelname,
                "logger":  record.name,
                "msg":     record.getMessage(),
            }
            if record.exc_info:
                log["exc"] = self.formatException(record.exc_info)
            return json.dumps(log, ensure_ascii=False)

    _handler = logging.StreamHandler()
    _handler.setFormatter(_JsonFormatter())
    logging.root.handlers = [_handler]
    logging.root.setLevel(logging.INFO)
    logger.info("[API] Log estruturado JSON ativado")

# ----------------------------------------------------------
# CORS (#30)
# ----------------------------------------------------------

_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
if _raw_origins.strip() == "*":
    _cors_origins: List[str] = ["*"]
else:
    _cors_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(_frontend_path):
    app.mount("/dashboard", StaticFiles(directory=_frontend_path, html=True), name="dashboard")

# ----------------------------------------------------------
# ROUTERS
# ----------------------------------------------------------

app.include_router(backtest_router)  # POST /backtest/run, GET /backtest/history (#2)

# ----------------------------------------------------------
# AUTH
# ----------------------------------------------------------

_API_TOKEN: Optional[str] = os.getenv("API_TOKEN") or None
_bearer_scheme = HTTPBearer(auto_error=False)

if not _API_TOKEN:
    logger.warning("[API] API_TOKEN não definido — POST /bot/* estão ABERTOS.")


def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
):
    if _API_TOKEN is None:
        return
    if credentials is None or credentials.credentials != _API_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido ou ausente.")


# ----------------------------------------------------------
# ESTADO GLOBAL
# ----------------------------------------------------------

_bot: Optional[RobotoBot] = None
_bot_thread: Optional[threading.Thread] = None
_last_signal: Optional[dict] = None
_client: Optional[BinanceClient] = None


def _get_client() -> BinanceClient:
    global _client
    if _client is None:
        _client = BinanceClient()
    return _client


_db = None

def _get_db():
    global _db
    if _db is None:
        try:
            from backend.db.supabase_client import SupabaseClient
            _db = SupabaseClient()
        except Exception as e:
            logger.warning(f"Supabase indisponível: {e}")
    return _db


_sentiment_analyzer = None

def _get_sentiment_analyzer():
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        from backend.analysis.sentiment import SentimentAnalyzer
        _sentiment_analyzer = SentimentAnalyzer()
    return _sentiment_analyzer


def _warmup_finbert_background():
    try:
        analyzer = _get_sentiment_analyzer()
        if not analyzer.is_model_loaded:
            logger.info("[Warmup] Iniciando pré-aquecimento do FinBERT...")
            ok = analyzer.warmup()
            logger.info(f"[Warmup] FinBERT: {'ok' if ok else 'falhou'}")
    except Exception as e:
        logger.error(f"[Warmup] Erro: {e}")


@app.on_event("startup")
async def startup_event():
    if os.getenv("WARMUP_ON_STARTUP", "false").lower() == "true":
        t = threading.Thread(target=_warmup_finbert_background, daemon=True)
        t.start()


# ----------------------------------------------------------
# SCHEMAS
# ----------------------------------------------------------

class BotConfig(BaseModel):
    symbol: str = "BTCUSDT"
    interval: str = "5m"
    balance: float = 10000.0
    only_strong: bool = True
    max_cycles: Optional[int] = None
    sleep_seconds: Optional[int] = None


# ----------------------------------------------------------
# HEALTH / STATUS
# ----------------------------------------------------------

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": "Roboto API", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
def health():
    """Liveness probe rápido. Não testa dependências."""
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/metrics/health", tags=["Health"])
def metrics_health():
    """
    Status detalhado de todas as dependências (#31).
    Binance, Supabase, FinBERT + uptime + version.
    """
    from backend.api.health import get_health
    return get_health()


@app.get("/status", tags=["Bot"])
def get_status():
    finbert_loaded = _get_sentiment_analyzer().is_model_loaded
    if _bot is None:
        return {
            "running": False, "paused": False, "symbol": None,
            "balance": None, "drawdown_pct": None,
            "trades_today": 0, "total_trades": 0,
            "open_trade": None, "finbert_loaded": finbert_loaded,
        }
    s = _bot.risk.status()
    ot = _bot.risk._open_trade
    return {
        "running": _bot._running,
        "paused": s["paused"],
        "pause_reason": s["pause_reason"],
        "symbol": _bot.symbol,
        "interval": _bot.interval,
        "balance": s["balance"],
        "initial_balance": s["initial_balance"],
        "drawdown_pct": s["drawdown_pct"],
        "trades_today": s["trades_today"],
        "total_trades": s["total_trades"],
        "consecutive_losses": s.get("consecutive_losses", 0),
        "finbert_loaded": finbert_loaded,
        "open_trade": {
            "id": ot.id, "direction": ot.direction,
            "entry_price": ot.entry_price,
            "stop_loss": ot.stop_loss, "take_profit": ot.take_profit,
            "opened_at": str(ot.opened_at),
        } if ot else None,
    }


@app.get("/warmup", tags=["Health"])
def warmup_model():
    analyzer = _get_sentiment_analyzer()
    if analyzer.is_model_loaded:
        return {"status": "already_loaded", "finbert_loaded": True}
    t = threading.Thread(target=_warmup_finbert_background, daemon=True)
    t.start()
    return {"status": "warming_up", "finbert_loaded": False}


# ----------------------------------------------------------
# SIGNALS
# ----------------------------------------------------------

@app.get("/signal", tags=["Signals"])
def get_last_signal():
    if _last_signal is None:
        return {"signal": None, "message": "Nenhum sinal gerado ainda"}
    return _last_signal


@app.get("/signals", tags=["Signals"])
def get_signals(
    symbol: str = Query("BTCUSDT"),
    limit: int = Query(50, ge=1, le=500),
):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Supabase indisponível")
    return {"signals": db.get_last_signals(symbol=symbol, limit=limit)}


# ----------------------------------------------------------
# TRADES
# ----------------------------------------------------------

@app.get("/trades", tags=["Trades"])
def get_trades():
    if _bot is None:
        return {"trades": [], "total": 0}
    trades = [
        {
            "id": t.id, "symbol": t.symbol, "direction": t.direction,
            "strength": t.strength, "entry_price": t.entry_price,
            "exit_price": t.exit_price, "stop_loss": t.stop_loss,
            "take_profit": t.take_profit, "pnl_pct": t.pnl_pct,
            "result": t.result, "opened_at": str(t.opened_at),
            "closed_at": str(t.closed_at),
        }
        for t in _bot.risk.closed_trades
    ]
    return {"trades": trades, "total": len(trades)}


@app.get("/trades/history", tags=["Trades"])
def get_trades_history(
    symbol: str = Query("BTCUSDT"),
    limit: int = Query(100, ge=1, le=500),
):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Supabase indisponível")
    return db.get_trades(symbol=symbol, limit=limit)


# ----------------------------------------------------------
# SESSIONS
# ----------------------------------------------------------

@app.get("/sessions", tags=["Sessions"])
def get_sessions():
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Supabase indisponível")
    try:
        res = db.client.table("bot_sessions") \
            .select("*").order("started_at", desc=True).limit(20).execute()
        return {"sessions": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------
# METRICS
# ----------------------------------------------------------

@app.get("/metrics", tags=["Metrics"])
def get_metrics():
    if _bot is None or not _bot.risk.closed_trades:
        return {"metrics": None, "message": "Sem trades suficientes"}
    from backend.risk.metrics import PerformanceMetrics
    result = PerformanceMetrics(_bot.risk.closed_trades).calculate()
    return {
        "total_trades": result.total_trades, "wins": result.wins, "losses": result.losses,
        "win_rate": result.win_rate, "profit_factor": result.profit_factor,
        "max_drawdown": result.max_drawdown, "sharpe_ratio": result.sharpe_ratio,
        "avg_win_pct": result.avg_win_pct, "avg_loss_pct": result.avg_loss_pct,
        "total_pnl_pct": result.total_pnl_pct, "approved": result.approved,
    }


# ----------------------------------------------------------
# REPORTS (#29)
# ----------------------------------------------------------

@app.get("/reports/summary", tags=["Reports"])
def get_reports_summary(symbol: str = Query("BTCUSDT")):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Supabase indisponível")
    trades = db.get_trades(symbol=symbol, limit=500)
    closed = [t for t in trades if t.get("result") in ("WIN", "LOSS")]
    if not closed:
        return {"symbol": symbol, "total_trades": 0, "win_rate": None, "pnl_total": None,
                "max_drawdown": None, "sharpe_ratio": None, "profit_factor": None}
    wins   = sum(1 for t in closed if t["result"] == "WIN")
    losses = sum(1 for t in closed if t["result"] == "LOSS")
    total  = len(closed)
    pnls   = [float(t["pnl_pct"] or 0) for t in closed]
    pnl_total    = round(sum(pnls), 4)
    win_rate     = round(wins / total * 100, 2) if total else 0
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss   = abs(sum(p for p in pnls if p < 0))
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else None
    equity = peak = max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak: peak = equity
        dd = peak - equity
        if dd > max_dd: max_dd = dd
    import statistics
    sharpe = None
    if len(pnls) >= 2:
        try:
            mu = statistics.mean(pnls); std = statistics.stdev(pnls)
            sharpe = round(mu / std * (252 ** 0.5), 4) if std > 0 else None
        except Exception: pass
    return {"symbol": symbol, "total_trades": total, "wins": wins, "losses": losses,
            "win_rate": win_rate, "pnl_total": pnl_total, "max_drawdown": round(max_dd, 4),
            "sharpe_ratio": sharpe, "profit_factor": profit_factor}


@app.get("/reports/trades", tags=["Reports"])
def get_reports_trades(
    symbol:    str           = Query("BTCUSDT"),
    result:    Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    page:      int           = Query(1, ge=1),
    per_page:  int           = Query(20, ge=1, le=100),
):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Supabase indisponível")
    all_trades = db.get_trades(symbol=symbol, limit=500)
    filtered   = all_trades
    if result:
        filtered = [t for t in filtered if t.get("result") == result.upper()]
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            filtered = [t for t in filtered if t.get("created_at") and
                datetime.fromisoformat(t["created_at"].replace("Z","+00:00")) >= dt_from]
        except ValueError: pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
            filtered = [t for t in filtered if t.get("created_at") and
                datetime.fromisoformat(t["created_at"].replace("Z","+00:00")) <= dt_to]
        except ValueError: pass
    total = len(filtered)
    start = (page - 1) * per_page
    return {"trades": filtered[start:start+per_page], "total": total,
            "page": page, "per_page": per_page, "total_pages": max(1, -(-total//per_page))}


@app.get("/reports/export/csv", tags=["Reports"])
def export_trades_csv(symbol: str = Query("BTCUSDT")):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Supabase indisponível")
    trades = db.get_trades(symbol=symbol, limit=500)
    cols   = ["id","symbol","direction","strength","entry_price","exit_price",
              "pnl_pct","result","created_at","closed_at"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for t in trades: writer.writerow({k: t.get(k, "") for k in cols})
    buf.seek(0)
    filename = f"roboto_trades_{symbol}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/reports/equity-curve", tags=["Reports"])
def get_equity_curve(symbol: str = Query("BTCUSDT")):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Supabase indisponível")
    trades = db.get_trades(symbol=symbol, limit=500)
    closed = [t for t in trades if t.get("result") in ("WIN","LOSS") and t.get("pnl_pct") is not None]
    try: closed.sort(key=lambda t: t.get("created_at") or "")
    except Exception: pass
    points = []
    equity = 0.0
    for t in closed:
        pnl = float(t["pnl_pct"]); equity += pnl
        points.append({"ts": t.get("closed_at") or t.get("created_at"),
                       "equity": round(equity, 4), "pnl_pct": round(pnl, 4)})
    return {"symbol": symbol, "points": points, "total": len(points)}


# ----------------------------------------------------------
# MARKET
# ----------------------------------------------------------

@app.get("/candles", tags=["Market"])
def get_candles(symbol: str = "BTCUSDT", interval: str = "5m", limit: int = 100):
    try:
        df = _get_client().get_candles(symbol=symbol, interval=interval, limit=limit)
        if df.empty:
            raise HTTPException(status_code=502, detail="Nenhum candle recebido")
        df_out = df[["open_time","open","high","low","close","volume"]].tail(50).copy()
        df_out["open_time"] = df_out["open_time"].astype(str)
        return {"candles": df_out.to_dict(orient="records"), "symbol": symbol, "interval": interval}
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/price", tags=["Market"])
def get_price(symbol: str = "BTCUSDT"):
    try:
        price = _get_client().get_price(symbol=symbol)
        return {"symbol": symbol, "price": price}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------
# BOT CONTROL
# ----------------------------------------------------------

@app.post("/bot/start", tags=["Bot"])
def start_bot(config: BotConfig, _: None = Depends(verify_token)):
    global _bot, _bot_thread
    if _bot and _bot._running:
        return {"status": "already_running", "symbol": _bot.symbol}
    _bot = RobotoBot(
        symbol=config.symbol, interval=config.interval,
        balance=config.balance, only_strong=config.only_strong,
        max_cycles=config.max_cycles, sleep_seconds=config.sleep_seconds,
    )
    _bot_thread = threading.Thread(target=_bot.run, daemon=True)
    _bot_thread.start()
    return {"status": "started", "symbol": config.symbol, "interval": config.interval}


@app.post("/bot/stop", tags=["Bot"])
def stop_bot(_: None = Depends(verify_token)):
    if _bot is None or not _bot._running:
        return {"status": "not_running"}
    _bot.stop()
    return {"status": "stopped"}


@app.post("/bot/resume", tags=["Bot"])
def resume_bot(_: None = Depends(verify_token)):
    if _bot is None:
        return {"status": "no_bot"}
    _bot.risk.resume()
    return {"status": "resumed"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api.routes:app", host="0.0.0.0", port=8000, reload=True)
