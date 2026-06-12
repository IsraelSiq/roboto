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
    """Decisão combinada técnico + sentimento, compatível com testes.

    Os testes constroem SignalDecision tanto via combine() quanto diretamente
    com kwargs como technical_signal, sentiment_signal, symbol, current_price,
    atr, etc. Campos extras são aceitos e armazenados em attrs.
    """

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
    current_price: Optional[float] = None
    atr: Optional[float] = None

    def __post_init__(self):
        # Se tech foi passado mas atr não, tenta extrair de tech
        if self.tech is not None and self.atr is None:
            self.atr = getattr(self.tech, "atr", None)
        if self.tech is not None and self.current_price is None:
            self.current_price = getattr(self.tech, "current_price", None)
        if self.technical_signal is None and self.tech is not None:
            self.technical_signal = getattr(self.tech, "signal", None)

    def direction(self) -> str:
        """Direção básica derivada do final."""
        if self.final in {CALL_FORTE, CALL_FRACO}:
            return "CALL"
        if self.final in {PUT_FORTE, PUT_FRACO}:
            return "PUT"
        return "AGUARDAR"

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
        symbol: str,
        timeframe: str,
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
            current_price=tech.current_price,
            atr=tech.atr,
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

    def generate(self, df):
        from backend.analysis.technical import TechnicalAnalysis

        df = TechnicalAnalysis.generate_signal(df.copy())
        signals: list[Signal] = []
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
