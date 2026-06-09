"""
Roboto — FastAPI REST
Expõe endpoints para o dashboard Streamlit e futura integração com Supabase/Vercel.

Endpoints:
    GET  /status          — status do bot (rodando, saldo, drawdown)
    GET  /signal          — último sinal gerado
    GET  /trades          — lista de trades fechados
    GET  /metrics         — métricas de performance
    GET  /candles         — últimos candles do símbolo
    POST /bot/start       — inicia o loop do bot
    POST /bot/stop        — para o loop do bot
    POST /bot/resume      — retoma após pausa por drawdown
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.core.bot import RobotoBot
from backend.market.binance_client import BinanceClient

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Roboto API",
    description="API do bot de trading Roboto",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estado global do bot
_bot: Optional[RobotoBot] = None
_bot_thread: Optional[threading.Thread] = None
_last_signal: Optional[dict] = None
_client = BinanceClient()


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
# ENDPOINTS
# ----------------------------------------------------------

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": "Roboto API", "version": "1.0.0"}


@app.get("/status", tags=["Bot"])
def get_status():
    """Status completo do bot."""
    if _bot is None:
        return {
            "running": False,
            "paused": False,
            "symbol": None,
            "balance": None,
            "drawdown_pct": None,
            "trades_today": 0,
            "total_trades": 0,
            "open_trade": None,
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
        "open_trade": {
            "id": ot.id,
            "direction": ot.direction,
            "entry_price": ot.entry_price,
            "stop_loss": ot.stop_loss,
            "take_profit": ot.take_profit,
            "opened_at": ot.opened_at,
        } if ot else None,
    }


@app.get("/signal", tags=["Signals"])
def get_last_signal():
    """Último sinal gerado pelo bot."""
    if _last_signal is None:
        return {"signal": None, "message": "Nenhum sinal gerado ainda"}
    return _last_signal


@app.get("/trades", tags=["Trades"])
def get_trades():
    """Lista de todos os trades fechados."""
    if _bot is None:
        return {"trades": [], "total": 0}
    trades = [
        {
            "id": t.id,
            "symbol": t.symbol,
            "direction": t.direction,
            "strength": t.strength,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "pnl_pct": t.pnl_pct,
            "result": t.result,
            "opened_at": t.opened_at,
            "closed_at": t.closed_at,
        }
        for t in _bot.risk.closed_trades
    ]
    return {"trades": trades, "total": len(trades)}


@app.get("/metrics", tags=["Metrics"])
def get_metrics():
    """Métricas de performance."""
    if _bot is None or not _bot.risk.closed_trades:
        return {"metrics": None, "message": "Sem trades suficientes"}
    from backend.risk.metrics import PerformanceMetrics
    result = PerformanceMetrics(_bot.risk.closed_trades).calculate()
    return {
        "total_trades": result.total_trades,
        "wins": result.wins,
        "losses": result.losses,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "max_drawdown": result.max_drawdown,
        "sharpe_ratio": result.sharpe_ratio,
        "avg_win_pct": result.avg_win_pct,
        "avg_loss_pct": result.avg_loss_pct,
        "total_pnl_pct": result.total_pnl_pct,
        "approved": result.approved,
    }


@app.get("/candles", tags=["Market"])
def get_candles(symbol: str = "BTCUSDT", interval: str = "5m", limit: int = 100):
    """Últimos candles do símbolo."""
    try:
        df = _client.get_candles(symbol=symbol, interval=interval, limit=limit)
        records = df[["open", "high", "low", "close", "volume"]].tail(50).reset_index()
        records["timestamp"] = records["timestamp"].astype(str)
        return {"candles": records.to_dict(orient="records"), "symbol": symbol, "interval": interval}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/bot/start", tags=["Bot"])
def start_bot(config: BotConfig):
    """Inicia o loop do bot em background."""
    global _bot, _bot_thread
    if _bot and _bot._running:
        return {"status": "already_running", "symbol": _bot.symbol}

    _bot = RobotoBot(
        symbol=config.symbol,
        interval=config.interval,
        balance=config.balance,
        only_strong=config.only_strong,
        max_cycles=config.max_cycles,
        sleep_seconds=config.sleep_seconds,
    )
    _bot_thread = threading.Thread(target=_bot.run, daemon=True)
    _bot_thread.start()
    return {"status": "started", "symbol": config.symbol, "interval": config.interval}


@app.post("/bot/stop", tags=["Bot"])
def stop_bot():
    """Para o loop do bot."""
    if _bot is None or not _bot._running:
        return {"status": "not_running"}
    _bot.stop()
    return {"status": "stopped"}


@app.post("/bot/resume", tags=["Bot"])
def resume_bot():
    """Retoma o bot após pausa por drawdown."""
    if _bot is None:
        return {"status": "no_bot"}
    _bot.risk.resume()
    return {"status": "resumed"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api.routes:app", host="0.0.0.0", port=8000, reload=True)
