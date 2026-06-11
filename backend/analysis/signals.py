"""
Roboto — Núcleo de Sinais
Combina sinal técnico (RSI+MACD+EMA+BB) com sentiment (FinBERT)
e gera a decisão final de trading.

Tabela de decisão:
    Técnico   | Sentiment | Decisão
    ----------|-----------|------------------
    CALL      | positive  | CALL_FORTE
    CALL      | neutral   | CALL_FRACO
    CALL      | negative  | AGUARDAR
    PUT       | negative  | PUT_FORTE
    PUT       | neutral   | PUT_FRACO
    PUT       | positive  | AGUARDAR
    AGUARDAR  | qualquer  | AGUARDAR

Log detalhado (#9):
    - Nível DEBUG exibe breakdown completo por componente
    - Nível INFO mantém formato original (compatível com parsers existentes)
    - SignalDecision agora expõe:
        sentiment_raw       → raw scores do FinBERT {positive, negative, neutral}
        sentiment_source    → origem do sentiment ('finbert'|'cache'|'fallback_*')
        sentiment_reason    → motivo detalhado do sentiment
    - WARNING emitido quando sentiment_source começa com 'fallback'
    - WARNING emitido quando sentiment_score é suspeito (== 0.50 exato)

Uso:
    from backend.analysis.signals import SignalCombiner
    combiner = SignalCombiner()
    decision = combiner.combine(technical_result, sentiment_result)
    print(decision.final)             # CALL_FORTE | PUT_FORTE | CALL_FRACO | PUT_FRACO | AGUARDAR
    print(decision.sentiment_raw)     # {'positive': 0.82, 'negative': 0.10, 'neutral': 0.08}
    print(decision.sentiment_source)  # 'finbert' | 'fallback_newsapi_error' | ...
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

from backend.analysis.technical import TechnicalResult
from backend.analysis.sentiment import SentimentResult, _is_suspicious_score

load_dotenv()
logger = logging.getLogger(__name__)

# Decisões possíveis
CALL_FORTE = "CALL_FORTE"
CALL_FRACO = "CALL_FRACO"
PUT_FORTE  = "PUT_FORTE"
PUT_FRACO  = "PUT_FRACO"
AGUARDAR   = "AGUARDAR"


@dataclass
class SignalDecision:
    """Decisão final combinada do robô."""
    final: str                        # CALL_FORTE | PUT_FORTE | CALL_FRACO | PUT_FRACO | AGUARDAR
    technical_signal: str             # CALL | PUT | AGUARDAR
    sentiment_signal: str             # positive | negative | neutral
    reason: str                       # explicação completa
    confidence: float                 # 0.0 – 1.0
    symbol: str = "BTCUSDT"
    timeframe: str = "5m"
    timestamp: str = ""

    # Métricas técnicas
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    ema50: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    current_price: Optional[float] = None
    sentiment_score: Optional[float] = None
    news_count: int = 0

    # Campos novos para diagnóstico (#9 + #5)
    sentiment_raw: dict = field(default_factory=dict)
    # ex: {'positive': 0.82, 'negative': 0.10, 'neutral': 0.08}
    sentiment_source: str = "finbert"
    # 'finbert' | 'cache' | 'fallback_no_news' | 'fallback_newsapi_error' | ...
    sentiment_reason: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def is_actionable(self) -> bool:
        return self.final != AGUARDAR

    def is_strong(self) -> bool:
        return self.final in (CALL_FORTE, PUT_FORTE)

    def direction(self) -> str:
        if self.final in (CALL_FORTE, CALL_FRACO):
            return "CALL"
        if self.final in (PUT_FORTE, PUT_FRACO):
            return "PUT"
        return "AGUARDAR"

    def strength(self) -> str:
        if self.final in (CALL_FORTE, PUT_FORTE):
            return "FORTE"
        if self.final in (CALL_FRACO, PUT_FRACO):
            return "FRACO"
        return "-"

    def summary(self) -> str:
        emoji = {
            CALL_FORTE: "✅ CALL FORTE",
            CALL_FRACO: "⚠️ CALL FRACO",
            PUT_FORTE:  "✅ PUT FORTE",
            PUT_FRACO:  "⚠️ PUT FRACO",
            AGUARDAR:   "⏸️ AGUARDAR",
        }
        price_str = f"${self.current_price:,.2f}" if self.current_price else "N/A"
        score_str = f"{self.sentiment_score:.2f}" if self.sentiment_score is not None else "N/A"
        return (
            f"{emoji.get(self.final, self.final)} | "
            f"Preço: {price_str} | "
            f"RSI: {self.rsi} | "
            f"Sentiment: {self.sentiment_signal} ({score_str}) | "
            f"Confiança: {self.confidence:.0%}"
        )

    def debug_breakdown(self) -> str:
        """Breakdown completo por componente para log DEBUG."""
        fallback_tag = " ⚠️ FALLBACK" if self.sentiment_source.startswith("fallback") else ""
        raw_str = (
            f"pos={self.sentiment_raw.get('positive', 0):.3f} "
            f"neg={self.sentiment_raw.get('negative', 0):.3f} "
            f"neu={self.sentiment_raw.get('neutral', 0):.3f}"
            if self.sentiment_raw else "N/A"
        )
        price_str = f"${self.current_price:,.2f}" if self.current_price else "N/A"
        score_str = f"{self.sentiment_score:.2f}" if self.sentiment_score is not None else "N/A"
        return (
            f"\n┌─ SignalCombiner Breakdown ── {self.symbol} {self.timeframe} ──────────────────\n"
            f"│  Preço atual    : {price_str}\n"
            f"│  RSI(14)        : {self.rsi}\n"
            f"│  EMA50          : {self.ema50}\n"
            f"│  MACD           : {self.macd} | Signal: {self.macd_signal}\n"
            f"│  Bollinger      : upper={self.bb_upper} lower={self.bb_lower}\n"
            f"│  Técnico        : {self.technical_signal}\n"
            f"│  FinBERT raw    : {raw_str}\n"
            f"│  Sentiment      : {self.sentiment_signal} (score={score_str}){fallback_tag}\n"
            f"│  Sent. source   : {self.sentiment_source}\n"
            f"│  Sent. reason   : {self.sentiment_reason}\n"
            f"│  Notícias       : {self.news_count}\n"
            f"│  Confiança final: {self.confidence:.0%}\n"
            f"└─ Decisão        : {self.final} ─────────────────────────────"
        )


class SignalCombiner:
    """
    Núcleo do robô — combina sinal técnico + sentiment.

    Args:
        symbol:      Par de trading (ex: 'BTCUSDT')
        timeframe:   Timeframe (ex: '5m')
        only_strong: Se True, só retorna CALL_FORTE e PUT_FORTE
    """

    DECISION_TABLE = {
        ("CALL",     "positive"): CALL_FORTE,
        ("CALL",     "neutral"):  CALL_FRACO,
        ("CALL",     "negative"): AGUARDAR,
        ("PUT",      "negative"): PUT_FORTE,
        ("PUT",      "neutral"):  PUT_FRACO,
        ("PUT",      "positive"): AGUARDAR,
        ("AGUARDAR", "positive"): AGUARDAR,
        ("AGUARDAR", "neutral"):  AGUARDAR,
        ("AGUARDAR", "negative"): AGUARDAR,
    }

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        timeframe: str = "5m",
        only_strong: bool = False,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.only_strong = only_strong

    def combine(
        self,
        technical: TechnicalResult,
        sentiment: SentimentResult,
    ) -> SignalDecision:
        """
        Combina sinal técnico + sentiment e retorna a decisão final.
        """
        tech_signal = technical.signal
        sent_signal = sentiment.signal

        final = self.DECISION_TABLE.get((tech_signal, sent_signal), AGUARDAR)

        if self.only_strong and final in (CALL_FRACO, PUT_FRACO):
            final = AGUARDAR

        confidence = self._calc_confidence(final, sentiment.score)
        reason = self._build_reason(final, technical, sentiment)

        decision = SignalDecision(
            final=final,
            technical_signal=tech_signal,
            sentiment_signal=sent_signal,
            reason=reason,
            confidence=confidence,
            symbol=self.symbol,
            timeframe=self.timeframe,
            rsi=technical.rsi,
            macd=technical.macd,
            macd_signal=technical.macd_signal,
            ema50=technical.ema50,
            bb_upper=technical.bb_upper,
            bb_lower=technical.bb_lower,
            current_price=technical.current_price,
            sentiment_score=sentiment.score,
            news_count=sentiment.news_count,
            sentiment_raw=getattr(sentiment, "raw_scores", {}),
            sentiment_source=getattr(sentiment, "source", "finbert"),
            sentiment_reason=sentiment.reason,
        )

        # Alertas de diagnóstico (#5)
        if decision.sentiment_source.startswith("fallback"):
            logger.warning(
                f"[Signal] FALLBACK detectado: sentiment_source='{decision.sentiment_source}' "
                f"para {self.symbol}. O bot pode estar operando sem dados reais de sentiment."
            )

        if (
            decision.sentiment_score is not None
            and _is_suspicious_score(decision.sentiment_score)
            and sent_signal != "neutral"
        ):
            logger.warning(
                f"[Signal] Score suspeito: sentiment_score=0.50 exato para sinal '{sent_signal}'. "
                "Possível fallback estático — verifique o FinBERT."
            )

        logger.info(f"[Signal] {decision.summary()}")
        logger.debug(decision.debug_breakdown())

        return decision

    @staticmethod
    def _calc_confidence(final: str, sentiment_score: float) -> float:
        if final == AGUARDAR:
            return 0.0
        if final in (CALL_FORTE, PUT_FORTE):
            return round(min(0.75 + sentiment_score * 0.25, 1.0), 4)
        # FRACO
        return round(min(0.50 + sentiment_score * 0.15, 0.75), 4)

    @staticmethod
    def _build_reason(final: str, tech: TechnicalResult, sent: SentimentResult) -> str:
        parts = [
            f"Técnico: {tech.signal} ({tech.reason})",
            f"Sentiment: {sent.signal} | score={sent.score:.4f} | {sent.news_count} notícias ({sent.reason})",
            f"Decisão: {final}",
        ]
        return " || ".join(parts)
