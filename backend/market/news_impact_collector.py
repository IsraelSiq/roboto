"""
Roboto — News Impact Collector
Persiste notícias + sentiment + preço no momento da coleta no Supabase.
Um job de backfill preenche price_1h/4h/24h e impact_pct após o tempo decorrido.

Fluxo:
    1. Bot coleta notícia + análise FinBERT + preço atual
    2. collector.collect() → salva na tabela news_impact (price_1h = NULL)
    3. A cada ciclo: collector.backfill_impacts() → preenche impactos históricos
    4. NewsImpactAnalyzer consulta esses dados para gerar impact_score

Uso:
    collector = NewsImpactCollector(binance_client, supabase_client)
    collector.collect(
        news={"title": "...", "published_at": "...", "source": "..."},
        symbol="BNBUSDT",
        keyword="bnb",
        sentiment_signal="positive",
        sentiment_score=0.82,
        price_now=650.0,
    )
    collector.backfill_impacts(symbol="BNBUSDT")
"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Janelas de impacto monitoradas (em horas)
_HORIZONS_H = {"1h": 1, "4h": 4, "24h": 24}


def _news_id(title: str) -> str:
    """Hash SHA256 dos primeiros 200 chars do título — ID determinístico."""
    return hashlib.sha256(title[:200].encode()).hexdigest()[:40]


class NewsImpactCollector:
    """
    Coleta e persiste o impacto histórico de notícias no preço do ativo.

    Args:
        binance_client: Instância de BinanceClient (para get_price e get_candles)
        db:             Instância de SupabaseClient
        min_age_hours:  Mínimo de horas para considerar um registro elegível
                        para backfill de price_1h (padrão: 1.1 para dar margem)
    """

    def __init__(self, binance_client, db, min_age_hours: float = 1.1):
        self.client = binance_client
        self.db = db
        self.min_age_hours = min_age_hours

    # ----------------------------------------------------------
    # COLETA
    # ----------------------------------------------------------

    def collect(
        self,
        news: dict,
        symbol: str,
        keyword: str,
        sentiment_signal: str,
        sentiment_score: float,
        price_now: float,
    ) -> bool:
        """
        Persiste uma notícia com o preço atual no Supabase.
        price_1h/4h/24h ficam NULL — preenchidos pelo backfill.

        Args:
            news:             Dict com title, published_at, source
            symbol:           Símbolo (ex: 'BNBUSDT')
            keyword:          Keyword usada na busca (ex: 'bnb')
            sentiment_signal: 'positive' | 'negative' | 'neutral'
            sentiment_score:  Float 0.0–1.0
            price_now:        Preço do ativo no momento da coleta

        Returns:
            True se inserido com sucesso, False se duplicata ou erro
        """
        title = (news.get("title") or "").strip()
        if not title:
            logger.warning("[NewsImpact] Notícia sem título — ignorada")
            return False

        news_id = _news_id(title)
        payload = {
            "news_id":          news_id,
            "symbol":           symbol,
            "keyword":          keyword,
            "title":            title,
            "source":           news.get("source", ""),
            "published_at":     news.get("published_at"),
            "collected_at":     datetime.now(timezone.utc).isoformat(),
            "sentiment_signal": sentiment_signal,
            "sentiment_score":  round(float(sentiment_score), 4),
            "price_at_news":    round(float(price_now), 4),
        }

        ok = self.db.insert_news_impact(payload)
        if ok:
            logger.info(
                f"[NewsImpact] Coletado: '{title[:60]}' | "
                f"{sentiment_signal} {sentiment_score:.2f} @ ${price_now:.2f}"
            )
        return ok

    # ----------------------------------------------------------
    # BACKFILL
    # ----------------------------------------------------------

    def backfill_impacts(self, symbol: str) -> int:
        """
        Busca registros com price_1h ainda NULL cuja coleta tem >= min_age_hours.
        Para cada um, consulta o preço histórico na Binance e calcula os impactos.

        Args:
            symbol: Símbolo para filtrar o backfill (ex: 'BNBUSDT')

        Returns:
            Número de registros atualizados
        """
        pending = self.db.get_news_impact_pending_backfill(symbol)
        if not pending:
            return 0

        updated = 0
        now_utc = datetime.now(timezone.utc)

        for row in pending:
            collected_at_str = row.get("collected_at")
            if not collected_at_str:
                continue

            # Parse da data de coleta
            try:
                collected_at = datetime.fromisoformat(
                    collected_at_str.replace("Z", "+00:00")
                )
            except ValueError:
                continue

            age_hours = (now_utc - collected_at).total_seconds() / 3600

            # Ainda não passou 1h — ainda cedo para backfill
            if age_hours < self.min_age_hours:
                continue

            patch = self._calculate_impact_patch(
                row_id=row["id"],
                symbol=symbol,
                price_at_news=row["price_at_news"],
                sentiment_signal=row["sentiment_signal"],
                collected_at=collected_at,
                age_hours=age_hours,
            )

            if patch:
                ok = self.db.update_news_impact(row["id"], patch)
                if ok:
                    updated += 1

        if updated:
            logger.info(f"[NewsImpact] Backfill: {updated} registros atualizados para {symbol}")
        return updated

    def _calculate_impact_patch(
        self,
        row_id: str,
        symbol: str,
        price_at_news: float,
        sentiment_signal: str,
        collected_at: datetime,
        age_hours: float,
    ) -> Optional[dict]:
        """
        Calcula os campos de impacto para um registro de news_impact.
        Retorna dict com os campos a atualizar, ou None se não foi possível.
        """
        patch = {}

        for col_suffix, horizon_h in _HORIZONS_H.items():
            # Só tenta preencher se tempo decorrido suficiente
            if age_hours < horizon_h:
                continue

            price_col  = f"price_{col_suffix}"
            impact_col = f"impact_pct_{col_suffix}"

            # Já preenchido — pula
            if patch.get(price_col) is not None:
                continue

            target_time = collected_at + timedelta(hours=horizon_h)
            price = self._get_price_at(
                symbol=symbol,
                target_time=target_time,
            )

            if price is not None and price_at_news and price_at_news > 0:
                impact_pct = round(
                    (price - price_at_news) / price_at_news * 100, 4
                )
                patch[price_col]  = round(price, 4)
                patch[impact_col] = impact_pct

        # direction_confirmed_1h: True se sinal positivo + preço subiu, ou negativo + caiu
        if "impact_pct_1h" in patch:
            impact_1h = patch["impact_pct_1h"]
            if sentiment_signal == "positive":
                patch["direction_confirmed_1h"] = impact_1h > 0
            elif sentiment_signal == "negative":
                patch["direction_confirmed_1h"] = impact_1h < 0
            else:
                patch["direction_confirmed_1h"] = None

        return patch if patch else None

    def _get_price_at(
        self,
        symbol: str,
        target_time: datetime,
        interval: str = "1h",
    ) -> Optional[float]:
        """
        Busca o preço de fechamento do candle mais próximo de target_time.
        Usa get_candles com limit=1 e o timestamp como âncora.

        Returns:
            Preço de fechamento (float) ou None se falhar
        """
        try:
            # Busca candle pela data usando BinanceClient
            df = self.client.get_candles(
                symbol=symbol,
                interval=interval,
                limit=2,
                end_time=int(target_time.timestamp() * 1000),
            )
            if df is not None and not df.empty:
                return float(df["close"].iloc[-1])
        except Exception as e:
            logger.debug(f"[NewsImpact] Erro ao buscar preço em {target_time}: {e}")
        return None
