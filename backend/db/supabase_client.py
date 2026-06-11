"""
Roboto — Supabase Client
Persiste sinais, trades, sessões e cache de notícias no banco.

Tabelas utilizadas (conforme schema real do projeto):
    signals      — sinais gerados a cada ciclo
    trades       — trades abertos/fechados
    bot_sessions — sessões do bot
    news_cache   — notícias já processadas pelo FinBERT (com TTL, #15)
    backtest_runs— resultados de backtests (Fase 8)
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
logger = logging.getLogger(__name__)


class SupabaseClient:
    """
    Wrapper do cliente Supabase para o Roboto.
    Instancia automaticamente via .env:
        SUPABASE_URL — URL do projeto
        SUPABASE_KEY — anon/service key
    """

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL e SUPABASE_KEY devem estar no .env")
        self.client: Client = create_client(url, key)
        logger.info("SupabaseClient inicializado")

    # ----------------------------------------------------------
    # BOT SESSIONS
    # ----------------------------------------------------------

    def create_session(self, symbol: str, interval: str, balance: float) -> Optional[str]:
        """Cria uma nova sessão e retorna o UUID gerado."""
        try:
            res = self.client.table("bot_sessions").insert({
                "symbol":      symbol,
                "interval":    interval,
                "balance_ini": balance,
                "status":      "running",
            }).execute()
            session_id = res.data[0]["id"]
            logger.info(f"[Supabase] Sessão criada: {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"[Supabase] Erro ao criar sessão: {e}")
            return None

    def close_session(self, session_id: str, balance_end: float, cycles: int, status: str = "stopped"):
        """Fecha a sessão com saldo final e total de ciclos."""
        try:
            self.client.table("bot_sessions").update({
                "balance_end": balance_end,
                "ended_at":    datetime.now(timezone.utc).isoformat(),
                "cycles":      cycles,
                "status":      status,
            }).eq("id", session_id).execute()
            logger.info(f"[Supabase] Sessão encerrada: {session_id}")
        except Exception as e:
            logger.error(f"[Supabase] Erro ao fechar sessão: {e}")

    # ----------------------------------------------------------
    # SIGNALS
    # ----------------------------------------------------------

    def save_signal(self, signal: dict, session_id: Optional[str] = None) -> Optional[str]:
        """
        Persiste um sinal gerado pelo SignalCombiner.
        Mapeia para as colunas reais da tabela signals.
        """
        try:
            res = self.client.table("signals").insert({
                "symbol":           signal.get("symbol", "BTCUSDT"),
                "timeframe":        signal.get("interval", "5m"),
                "technical_signal": signal.get("technical_signal"),
                "sentiment_signal": signal.get("sentiment_signal"),
                "final_decision":   signal.get("final"),
                "rsi":              signal.get("rsi"),
                "current_price":    signal.get("current_price"),
                "sentiment_score":  signal.get("sentiment_score"),
                "reason":           signal.get("reason"),
                "cycle":            signal.get("cycle"),
                "mode":             signal.get("mode", "paper"),
            }).execute()
            signal_id = res.data[0]["id"]
            logger.debug(f"[Supabase] Sinal salvo: {signal_id}")
            return signal_id
        except Exception as e:
            logger.error(f"[Supabase] Erro ao salvar sinal: {e}")
            return None

    def get_last_signals(self, symbol: str = "BTCUSDT", limit: int = 50) -> list:
        """Retorna os últimos N sinais de um símbolo."""
        try:
            res = (
                self.client.table("signals")
                .select("*")
                .eq("symbol", symbol)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data
        except Exception as e:
            logger.error(f"[Supabase] Erro ao buscar sinais: {e}")
            return []

    # ----------------------------------------------------------
    # TRADES
    # ----------------------------------------------------------

    def save_trade(self, trade, signal_id: Optional[str] = None):
        """
        Persiste um trade aberto.
        `trade` é o objeto TradeRecord do RiskManager.
        """
        try:
            self.client.table("trades").upsert({
                "id":          str(trade.id),
                "signal_id":   signal_id,
                "symbol":      trade.symbol,
                "direction":   trade.direction,
                "strength":    trade.strength,
                "entry_price": trade.entry_price,
                "exit_price":  trade.exit_price,
                "pnl_pct":     trade.pnl_pct,
                "result":      trade.result or "PENDING",
                "closed_at":   trade.closed_at,
                "mode":        "paper",
            }).execute()
            logger.debug(f"[Supabase] Trade salvo: {trade.id} | {trade.result}")
        except Exception as e:
            logger.error(f"[Supabase] Erro ao salvar trade: {e}")

    def get_trades(self, symbol: str = "BTCUSDT", limit: int = 100) -> list:
        """Retorna os últimos N trades de um símbolo."""
        try:
            res = (
                self.client.table("trades")
                .select("*")
                .eq("symbol", symbol)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data
        except Exception as e:
            logger.error(f"[Supabase] Erro ao buscar trades: {e}")
            return []

    # ----------------------------------------------------------
    # NEWS CACHE (#15)
    # ----------------------------------------------------------

    def get_cached_news(
        self,
        symbol: str,
        ttl_minutes: int = 15,
        limit: int = 10,
    ) -> list[dict]:
        """
        Retorna notícias recentes do cache Supabase dentro do TTL.

        Filtra por `created_at > now() - ttl_minutes` no lado do cliente
        (compatível com qualquer tier do Supabase sem precisar de RPC).

        Args:
            symbol:      Símbolo do ativo (ex: 'BTCUSDT')
            ttl_minutes: Janela de validade do cache em minutos (padrão: 15)
            limit:       Máximo de notícias a retornar (padrão: 10)

        Returns:
            Lista de dicts com title/description/sentiment/score,
            ou lista vazia se cache expirado/vazio.
        """
        try:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
            ).isoformat()
            res = (
                self.client.table("news_cache")
                .select("title, description, sentiment, score, created_at")
                .eq("symbol", symbol)
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            rows = res.data or []
            if rows:
                logger.debug(
                    f"[NewsCache] Cache hit para '{symbol}': "
                    f"{len(rows)} notícias (TTL={ttl_minutes}min)"
                )
            return rows
        except Exception as e:
            logger.warning(f"[NewsCache] Erro ao consultar cache: {e}")
            return []

    def cache_news(self, symbol: str, articles: list):
        """
        Salva notícias processadas no cache para evitar reprocessamento.
        `articles` é lista de dicts com title, description, source, url,
        sentiment e score (preenchidos após análise do FinBERT).
        """
        try:
            rows = [
                {
                    "symbol":      symbol,
                    "title":       a.get("title", ""),
                    "description": a.get("description"),
                    "source":      a.get("source"),
                    "url":         a.get("url"),
                    "sentiment":   a.get("sentiment"),
                    "score":       a.get("score"),
                }
                for a in articles
            ]
            self.client.table("news_cache").insert(rows).execute()
            logger.debug(f"[Supabase] {len(rows)} notícias cacheadas para {symbol}")
        except Exception as e:
            logger.error(f"[Supabase] Erro ao cachear notícias: {e}")

    # ----------------------------------------------------------
    # BACKTEST RUNS (Fase 8)
    # ----------------------------------------------------------

    def save_backtest(self, result: dict) -> Optional[str]:
        """
        Persiste o resultado de um backtest.
        Campos: symbol, timeframe, period_start, period_end,
                total_trades, win_rate, profit_factor,
                max_drawdown, sharpe_ratio, approved, notes
        """
        try:
            res = self.client.table("backtest_runs").insert(result).execute()
            run_id = res.data[0]["id"]
            logger.info(f"[Supabase] Backtest salvo: {run_id}")
            return run_id
        except Exception as e:
            logger.error(f"[Supabase] Erro ao salvar backtest: {e}")
            return None

    def get_backtests(self, symbol: str = "BTCUSDT") -> list:
        """Retorna todos os backtests de um símbolo, do mais recente ao mais antigo."""
        try:
            res = (
                self.client.table("backtest_runs")
                .select("*")
                .eq("symbol", symbol)
                .order("created_at", desc=True)
                .execute()
            )
            return res.data
        except Exception as e:
            logger.error(f"[Supabase] Erro ao buscar backtests: {e}")
            return []
