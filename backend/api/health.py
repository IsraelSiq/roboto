"""
Roboto — Health Metrics (#31)
Endpoint GET /metrics/health — status detalhado de todas as dependências.

Retorna:
    {
      "status": "ok" | "degraded" | "offline",
      "uptime_s": 123.4,
      "version": "1.0.0",
      "ts": "2026-...",
      "dependencies": {
        "binance":  {"ok": true,  "latency_ms": 42, "mode": "TESTNET"},
        "supabase": {"ok": false, "error": "connection refused"},
        "finbert":  {"ok": true,  "loaded": true}
      }
    }

Status geral:
    ok       — todas as depends ok
    degraded — alguma dependência offline (bot pode continuar)
    offline  — Binance offline (bot não consegue operar)
"""

import time
from datetime import datetime, timezone

_START_TIME = time.time()
VERSION = "1.0.0"


def get_health() -> dict:
    """
    Verifica todas as dependências e retorna dict de saúde.
    Não lança exceções — cada depêndencia é isolada em try/except.
    """
    deps = {}

    # --- Binance ---
    try:
        from backend.market.binance_client import BinanceClient
        t0 = time.time()
        bc = BinanceClient()
        ok = bc.ping()
        latency = round((time.time() - t0) * 1000)
        deps["binance"] = {
            "ok": ok,
            "latency_ms": latency,
            "mode": "TESTNET" if bc.testnet else "REAL",
        }
    except Exception as e:
        deps["binance"] = {"ok": False, "error": str(e)[:100]}

    # --- Supabase ---
    try:
        from backend.db.supabase_client import SupabaseClient
        t0 = time.time()
        db = SupabaseClient()
        # Ping leve: busca 1 linha de qualquer tabela
        db.client.table("bot_sessions").select("id").limit(1).execute()
        latency = round((time.time() - t0) * 1000)
        deps["supabase"] = {"ok": True, "latency_ms": latency}
    except Exception as e:
        deps["supabase"] = {"ok": False, "error": str(e)[:100]}

    # --- FinBERT ---
    try:
        from backend.analysis.sentiment import _FINBERT_PIPELINE
        loaded = _FINBERT_PIPELINE is not None
        deps["finbert"] = {"ok": True, "loaded": loaded}
    except Exception as e:
        deps["finbert"] = {"ok": False, "loaded": False, "error": str(e)[:100]}

    # Status geral
    if not deps.get("binance", {}).get("ok"):
        overall = "offline"
    elif not deps.get("supabase", {}).get("ok"):
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status": overall,
        "uptime_s": round(time.time() - _START_TIME, 1),
        "version": VERSION,
        "ts": datetime.now(timezone.utc).isoformat(),
        "dependencies": deps,
    }
