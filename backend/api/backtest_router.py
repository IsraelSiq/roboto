"""
Roboto — Backtest API Router

Endpoints:
    POST /backtest/run      Roda um backtest e retorna resultado completo
    GET  /backtest/history  Lista runs salvos no Supabase
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.backtest.data_loader import BacktestDataLoader
from backend.backtest.engine import BacktestEngine
from backend.backtest.report import BacktestReporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="backtest")

DEFAULT_RISK = {
    "1m":  (0.3, 0.6),  "3m":  (0.5, 1.0),  "5m":  (0.8, 1.6),
    "15m": (1.5, 3.0),  "30m": (2.0, 4.0),  "1h":  (2.5, 5.0),
    "2h":  (3.0, 6.0),  "4h":  (4.0, 8.0),  "1d":  (5.0, 10.0),
}


class BacktestRequest(BaseModel):
    symbol:               str   = Field("BTCUSDT", description="Par de moedas")
    interval:             str   = Field("5m",       description="Timeframe")
    start:                str   = Field("2026-01-01",description="Data inicial YYYY-MM-DD")
    end:                  Optional[str] = Field(None, description="Data final (None = hoje)")
    balance:              float = Field(10000.0,    description="Saldo inicial USDT")
    sentiment_mode:       str   = Field("positive", description="neutral | positive | negative")
    only_strong:          bool  = Field(True,       description="Só sinais FORTES")
    use_atr_stop:         bool  = Field(False,      description="SL adaptativo por ATR")
    atr_multiplier:       float = Field(1.5,        description="Multiplicador ATR")
    rr_ratio:             float = Field(2.0,        description="Rão R:R para TP")
    macro_filter_enabled: bool  = Field(False,      description="Filtro de tendência macro")
    macro_timeframe:      str   = Field("1h",       description="TF do filtro macro")
    save:                 bool  = Field(True,       description="Salvar no Supabase")


def _run_backtest_sync(req: BacktestRequest) -> dict:
    """Executa o backtest de forma síncrona (rodado no thread pool)."""
    default_sl, default_tp = DEFAULT_RISK.get(req.interval, (1.0, 2.0))

    loader = BacktestDataLoader()
    df = loader.load(
        symbol=req.symbol,
        interval=req.interval,
        start=req.start,
        end=req.end,
    )
    if df.empty:
        raise ValueError(f"Nenhum dado retornado para {req.symbol} {req.interval} desde {req.start}")

    engine = BacktestEngine(
        symbol=req.symbol,
        interval=req.interval,
        balance=req.balance,
        only_strong=req.only_strong,
        stop_loss_pct=default_sl,
        take_profit_pct=default_tp,
        sentiment_mode=req.sentiment_mode,
        use_atr_stop=req.use_atr_stop,
        atr_multiplier=req.atr_multiplier,
        rr_ratio=req.rr_ratio,
        macro_filter_enabled=req.macro_filter_enabled,
        macro_resample_tf=req.macro_timeframe,
    )
    result = engine.run(df)

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

    if req.save:
        try:
            BacktestReporter().save(result)
        except Exception as e:
            logger.warning(f"[BacktestAPI] Erro ao salvar no Supabase: {e}")

    return {
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
    }


@router.post("/run", summary="Rodar backtest")
async def run_backtest(req: BacktestRequest):
    """
    Executa o backtest sobre dados históricos da Binance.
    Pode levar de 10 a 60 segundos dependendo do período e timeframe.
    """
    logger.info(
        f"[BacktestAPI] run: {req.symbol} {req.interval} "
        f"{req.start}→{req.end or 'hoje'} | "
        f"atr={req.use_atr_stop} macro={req.macro_filter_enabled}"
    )
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _run_backtest_sync, req)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"[BacktestAPI] Erro inesperado: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {e}")


@router.get("/history", summary="Histórico de backtests")
async def backtest_history(
    symbol:   Optional[str] = Query(None),
    limit:    int           = Query(20, ge=1, le=100),
):
    """
    Lista os últimos backtest runs salvos no Supabase.
    """
    try:
        reporter = BacktestReporter()
        runs = reporter.list_runs(symbol=symbol, limit=limit)
        return {"runs": runs, "total": len(runs)}
    except Exception as e:
        logger.warning(f"[BacktestAPI] Erro ao listar histórico: {e}")
        return {"runs": [], "total": 0}
