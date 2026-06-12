import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from backend.analysis.technical import TechnicalResult
from backend.analysis.sentiment import SentimentResult

logger = logging.getLogger(__name__)

CALL_FORTE = "CALL_FORTE"
CALL_FRACO = "CALL_FRACO"
PUT_FORTE = "PUT_FORTE"
PUT_FRACO = "PUT_FRACO"
AGUARDAR = "AGUARDAR"


@dataclass
class SignalDecision:
    """Decisão combinada técnico + sentimento, compatível com testes."""

    final: str
    confidence: float = 0.0
    sentiment_raw: Dict[str, float] = field(default_factory=dict)
    sentiment_source: str = ""
    sentiment_reason: str = ""
    tech: Optional[TechnicalResult] = None
    sentiment: Optional[SentimentResult] = None

    # campos extras usados em testes / RiskManager
    technical_signal: Optional[str] = None
    sentiment_signal: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: str | None = None
    current_price: Optional[float] = None
    atr: Optional[float] = None
    reason: str = ""
    rsi: float | None = None
    sentiment_score: float | None = None
    news_count: int | None = None

    def __post_init__(self):
        # Se tech foi passado mas campos não, tenta extrair de tech
        if self.tech is not None:
            if self.atr is None:
                self.atr = getattr(self.tech, "atr", None)
            if self.current_price is None:
                self.current_price = getattr(self.tech, "current_price", None)
            if self.rsi is None:
                self.rsi = getattr(self.tech, "rsi", None)
            if self.technical_signal is None:
                self.technical_signal = getattr(self.tech, "signal", None)

        if self.sentiment is not None:
            if self.sentiment_score is None:
                self.sentiment_score = self.sentiment.score
            if self.news_count is None:
                self.news_count = getattr(self.sentiment, "news_count", None)

    def direction(self) -> str:
        """Direção básica derivada do final."""
        if self.final in {CALL_FORTE, CALL_FRACO}:
            return "CALL"
        if self.final in {PUT_FORTE, PUT_FRACO}:
            return "PUT"
        return "AGUARDAR"

    def strength(self) -> str:
        """Força do sinal com base no final (forte vs fraco)."""
        if self.final in {CALL_FORTE, PUT_FORTE}:
            return "strong"
        if self.final in {CALL_FRACO, PUT_FRACO}:
            return "weak"
        return "none"

    # Método compatível com RiskManager.only_strong
    def is_strong(self) -> bool:
        return self.strength() == "strong"

    def debug_breakdown(self) -> str:
        parts = []
        if self.tech is not None:
            parts.extend([
                f"RSI: {self.tech.rsi}",
                f"EMA50: {self.tech.ema50}",
                f"MACD: {self.tech.macd}",
            ])
        parts.append(f"FinBERT raw: {self.sentiment_raw}")
        if self.sentiment is not None:
            parts.append(f"Sentiment: {self.sentiment.signal} ({self.sentiment.score:.3f})")
        parts.append(f"Decisão: {self.final}")
        if "fallback" in (self.sentiment_source or "").lower():
            parts.append("FALLBACK: fonte de sentimento em modo de contingência")
        return " | ".join(parts)


class SignalCombiner:
    """Combina sinal técnico e de sentimento em uma decisão final."""

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        timeframe: str = "5m",
        only_strong: bool = False,
        macro_filter: Any = None,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.only_strong = only_strong
        self.macro_filter = macro_filter

    def _base_decision(self, tech_signal: str, sent_signal: str) -> str:
        table = {
            ("CALL", "positive"): CALL_FORTE,
            ("CALL", "neutral"): CALL_FRACO,
            ("CALL", "negative"): AGUARDAR,
            ("PUT", "negative"): PUT_FORTE,
            ("PUT", "neutral"): PUT_FRACO,
            ("PUT", "positive"): AGUARDAR,
            ("AGUARDAR", "positive"): AGUARDAR,
            ("AGUARDAR", "neutral"): AGUARDAR,
            ("AGUARDAR", "negative"): AGUARDAR,
        }
        return table.get((tech_signal, sent_signal), AGUARDAR)

    def combine(self, tech: TechnicalResult, sentiment: SentimentResult) -> SignalDecision:
        final = self._base_decision(tech.signal, sentiment.signal)

        if "fallback" in (sentiment.source or "").lower():
            logger.warning("FALLBACK de sentimento ativo: %s", sentiment.source)

        # aplica macro filter se existir e sinal não for AGUARDAR
        if self.macro_filter is not None and tech.signal != "AGUARDAR":
            allowed = self.macro_filter(tech=tech, sentiment=sentiment)
            if allowed is False:
                final = AGUARDAR

        # confiança simples baseada no score de sentimento
        base_score = min(max(sentiment.score, 0.0), 1.0)
        if final in {CALL_FORTE, PUT_FORTE}:
            confidence = base_score
        elif final in {CALL_FRACO, PUT_FRACO}:
            confidence = 0.5 * base_score
        else:
            confidence = 0.0

        if self.only_strong and final in {CALL_FRACO, PUT_FRACO}:
            final = AGUARDAR
            confidence = 0.0

        decision = SignalDecision(
            final=final,
            confidence=confidence,
            sentiment_raw=sentiment.raw_scores,
            sentiment_source=sentiment.source,
            sentiment_reason=sentiment.reason,
            tech=tech,
            sentiment=sentiment,
            symbol=self.symbol,
            timeframe=self.timeframe,
            current_price=tech.current_price,
            atr=tech.atr,
        )
        return decision
