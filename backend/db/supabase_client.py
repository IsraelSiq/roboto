"""
Roboto — Supabase Client
Persiste sinais, trades, sessões, cache de notícias e impacto de notícias.

Tabelas utilizadas:
    signals       — sinais gerados a cada ciclo
    trades        — trades abertos/fechados
    bot_sessions  — sessões do bot
    news_cache    — notícias já processadas pelo FinBERT (com TTL, #15)
    backtest_runs — resultados de backtests
    news_impact   — histórico de notícias + impacto no preço (#51/#52)
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
    # BACKTEST RUNS
    # ----------------------------------------------------------

    def save_backtest(self, result: dict) -> Optional[str]:
        """Persiste o resultado de um backtest."""
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

    # ----------------------------------------------------------
    # NEWS IMPACT (#51 / #52 / #53)
    # ----------------------------------------------------------

    def insert_news_impact(self, payload: dict) -> bool:
        """
        Insere um registro na tabela news_impact.
        Usa upsert por news_id para evitar duplicatas.

        Args:
            payload: Dict com os campos da tabela news_impact
                     (news_id, symbol, keyword, title, source,
                      published_at, collected_at, sentiment_signal,
                      sentiment_score, price_at_news)

        Returns:
            True se inserido, False se duplicata silenciosa ou erro
        """
        try:
            self.client.table("news_impact").upsert(
                payload,
                on_conflict="news_id",
                ignore_duplicates=True,
            ).execute()
            return True
        except Exception as e:
            logger.error(f"[Supabase] Erro ao inserir news_impact: {e}")
            return False

    def update_news_impact(self, row_id: str, patch: dict) -> bool:
        """
        Atualiza campos de impacto de um registro news_impact pelo UUID.

        Args:
            row_id: UUID do registro (campo 'id')
            patch:  Dict com campos a atualizar (ex: price_1h, impact_pct_1h)

        Returns:
            True se atualizado com sucesso
        """
        try:
            self.client.table("news_impact").update(patch).eq("id", row_id).execute()
            return True
        except Exception as e:
            logger.error(f"[Supabase] Erro ao atualizar news_impact {row_id}: {e}")
            return False

    def get_news_impact_pending_backfill(
        self,
        symbol: str,
        limit: int = 50,
    ) -> list[dict]:
        """
        Retorna registros de news_impact onde price_1h ainda é NULL.
        Usado pelo NewsImpactCollector.backfill_impacts().

        Args:
            symbol: Filtrar pelo símbolo (ex: 'BNBUSDT')
            limit:  Máximo de registros a retornar

        Returns:
            Lista de dicts com id, collected_at, price_at_news, sentiment_signal
        """
        try:
            res = (
                self.client.table("news_impact")
                .select("id, collected_at, price_at_news, sentiment_signal")
                .eq("symbol", symbol)
                .is_("price_1h", "null")
                .order("collected_at", desc=False)
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"[Supabase] Erro ao buscar news_impact pendentes: {e}")
            return []

    def get_similar_news_impacts(
        self,
        symbol: str,
        sentiment_signal: str,
        score_min: float,
        score_max: float,
        horizon: str = "1h",
        limit: int = 100,
    ) -> list[dict]:
        """
        Retorna registros históricos de news_impact que correspondem a:
        - mesmo symbol
        - mesmo sentiment_signal
        - sentiment_score entre score_min e score_max
        - impact_pct_{horizon} preenchido (não NULL)

        Usado pelo NewsImpactAnalyzer para calcular impact_score.

        Args:
            symbol:           Símbolo do ativo (ex: 'BNBUSDT')
            sentiment_signal: 'positive' | 'negative' | 'neutral'
            score_min:        Limite inferior do sentiment_score
            score_max:        Limite superior do sentiment_score
            horizon:          '1h' | '4h' | '24h'
            limit:            Máximo de registros

        Returns:
            Lista de dicts com impact_pct_{horizon}, sentiment_score,
            direction_confirmed_1h, collected_at
        """
        impact_col = f"impact_pct_{horizon}"
        try:
            res = (
                self.client.table("news_impact")
                .select(
                    f"id, sentiment_score, {impact_col}, "
                    "direction_confirmed_1h, collected_at"
                )
                .eq("symbol", symbol)
                .eq("sentiment_signal", sentiment_signal)
                .gte("sentiment_score", round(score_min, 4))
                .lte("sentiment_score", round(score_max, 4))
                .not_.is_(impact_col, "null")
                .order("collected_at", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"[Supabase] Erro ao buscar similar news impacts: {e}")
            return []

    def get_news_impact_stats(
        self,
        symbol: str,
        limit: int = 200,
    ) -> list[dict]:
        """
        Retorna todos os registros de news_impact com impacto preenchido.
        Útil para análise exploratória e dashboards.

        Args:
            symbol: Símbolo a filtrar
            limit:  Máximo de registros

        Returns:
            Lista de dicts com todos os campos da tabela
        """
        try:
            res = (
                self.client.table("news_impact")
                .select("*")
                .eq("symbol", symbol)
                .not_.is_("impact_pct_1h", "null")
                .order("collected_at", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"[Supabase] Erro ao buscar news_impact stats: {e}")
            return []
