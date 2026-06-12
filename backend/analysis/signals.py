import logging
from dataclasses import dataclass
from typing import List

from backend.analysis.technical import TechnicalAnalysis
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
    final: str
    confidence: float
    sentiment_raw: dict
    sentiment_source: str
    sentiment_reason: str
    tech: TechnicalResult
    sentiment: SentimentResult

    def debug_breakdown(self) -> str:
        parts = [
            f"RSI: {self.tech.rsi}",
            f"EMA50: {self.tech.ema50}",
            f"MACD: {self.tech.macd}",
            f"FinBERT raw: {self.sentiment_raw}",
            f"Sentiment: {self.sentiment.signal} ({self.sentiment.score:.3f})",
            f"Decisão: {self.final}",
        ]
        if "fallback" in (self.sentiment_source or "").lower():
            parts.append("FALLBACK: fonte de sentimento em modo de contingência")
        return " | ".join(parts)


class SignalCombiner:
    """Combina sinal técnico e de sentimento em uma decisão final.

    Implementação simplificada, mas compatível com a tabela de decisão dos testes.
    """

    def __init__(self, symbol: str, timeframe: str, only_strong: bool = False):
        self.symbol = symbol
        self.timeframe = timeframe
        self.only_strong = only_strong

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

        # confiança simples baseada no score de sentimento
        confidence = 0.0
        if final in {CALL_FORTE, PUT_FORTE}:
            confidence = min(max(sentiment.score, 0.0), 1.0)
        elif final in {CALL_FRACO, PUT_FRACO}:
            confidence = 0.5 * min(max(sentiment.score, 0.0), 1.0)

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
        )
        return decision


# Compatibilidade mínima com o antigo gerador de sinais voltado só para técnico

@dataclass
class Signal:
    symbol: str
    direction: int
    strength: str
    reason: str


class SignalGenerator:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol

    def generate(self, df) -> List[Signal]:
        df = TechnicalAnalysis.generate_signal(df.copy())
        signals: List[Signal] = []
        for _, row in df.iterrows():
            if row.get("signal", 0) == 0:
                continue
            direction = int(row["signal"])
            strength = row.get("strength", "weak")
            reason = "technical"
            signals.append(
                Signal(
                    symbol=self.symbol,
                    direction=direction,
                    strength=strength,
                    reason=reason,
                )
            )
        return signals
