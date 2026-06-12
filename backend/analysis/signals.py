"""
Roboto — Núcleo de Sinais ✉
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

Filtro macro (#8):
    Se macro_filter estiver ativo e tendência for desfavorável,
    final → AGUARDAR independente do sinal técnico/sentiment.
    SignalDecision.macro_blocked = True quando isso ocorre.

Fix #34:
    macro_ok == None (mercado lateral / dados insuficientes) agora é tratado
    como bloqueio conservador, igual a macro_ok == False.
    Isso alinha comportamento com o docstring e os logs do MacroTrendFilter.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

from backend.analysis.technical import TechnicalResult
from backend.analysis.sentiment import SentimentResult, _is_suspicious_score
from backend.market.symbols import SYMBOL_KEYWORDS

load_dotenv()
logger = logging.getLogger(__name__)

# Decisões possíveis
CALL_FORTE = "CALL_FORTE"
CALL_FRACO = "CALL_FRACO"
PUT_FORTE = "PUT_FORTE"
PUT_FRACO = "PUT_FRACO"
AGUARDAR = "AGUARDAR"


@dataclass
class SignalDecision:
    """Decisão final combinada do robô."""
    final: str
    technical_signal: str
    sentiment_signal: str
    reason: str
    confidence: float
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

    # ATR propagado de TechnicalResult (#7)
    atr: Optional[float] = None

    # Filtro macro (#8)
    macro_blocked: bool = False

    # --- Campos para diagnóstico (#9 + #5) ---
    sentiment_raw: dict = field(default_factory=dict)
    sentiment_source: str = "finbert"
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
        """Resumo INFO (formato original — não quebra parsers)."""
        emoji = {
            CALL_FORTE: "✅ CALL FORTE",
            CALL_FRACO: "⚠️  CALL FRACO",
            PUT_FORTE: "✅ PUT FORTE",
            PUT_FRACO: "⚠️  PUT FRACO",
            AGUARDAR: "⏸️  AGUARDAR",
        }
        score_str = f"{self.sentiment_score:.2f}" if self.sentiment_score is not None else "N/A"
        atr_str = f" | ATR: {self.atr:.2f}" if self.atr is not None else ""
        macro_str = " | 🚫 MACRO" if self.macro_blocked else ""
        return (
            f"{emoji.get(self.final, self.final)} | "
            f"Preço: ${self.current_price:,.2f} | "
            f"RSI: {self.rsi} | "
            f"Sentiment: {self.sentiment_signal} ({score_str}) | "
            f"Confiança: {self.confidence:.0%}"
            f"{atr_str}{macro_str}"
        )

    def debug_breakdown(self) -> str:
        """Breakdown detalhado para log DEBUG."""
        raw_str = (
            f"pos={self.sentiment_raw.get('positive', '?'):.3f} "
            f"neg={self.sentiment_raw.get('negative', '?'):.3f} "
            f"neu={self.sentiment_raw.get('neutral', '?'):.3f}"
        ) if self.sentiment_raw else "(não disponível)"

        source_flag = " ⚠️ FALLBACK" if self.sentiment_source.startswith("fallback") else ""

        lines = [
            f"┌─ SignalCombiner Breakdown ── {self.symbol} {self.timeframe} ──────────────────",
            f"│  Preço atual    : ${self.current_price:,.2f}",
            f"│  ATR(14)        : {self.atr}",
            f"│  RSI(14)        : {self.rsi}",
            f"│  EMA50          : {self.ema50}",
            f"│  MACD           : {self.macd} | Signal: {self.macd_signal}",
            f"│  Bollinger      : upper={self.bb_upper} lower={self.bb_lower}",
            f"│  Técnico        : {self.technical_signal}",
            f"│  FinBERT raw    : {raw_str}",
            f"│  Sentiment      : {self.sentiment_signal} (score={self.sentiment_score})",
            f"│  Sent. source   : {self.sentiment_source}{source_flag}",
            f"│  Sent. reason   : {self.sentiment_reason}",
            f"│  Notícias       : {self.news_count}",
            f"│  Macro bloqueio : {self.macro_blocked}",
            f"│  Confiança final: {self.confidence:.0%}",
            f"└─ Decisão        : {self.final} ────────────────────────────────────────────",
        ]
        return "\n".join(lines)


class SignalCombiner:
    """
    Núcleo do robô — combina sinal técnico + sentiment + filtro macro.

    Args:
        symbol:         Par de trading (ex: 'BTCUSDT')
        timeframe:      Timeframe (ex: '5m')
        only_strong:    Se True, só retorna CALL_FORTE e PUT_FORTE
        macro_filter:   Instância de MacroTrendFilter ou None para desativar
    """

    DECISION_TABLE = {
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

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        timeframe: str = "5m",
        only_strong: bool = False,
        macro_filter=None,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.only_strong = only_strong
        self.macro_filter = macro_filter  # MacroTrendFilter | None

    def combine(
        self,
        technical: TechnicalResult,
        sentiment: SentimentResult,
        df_macro: Optional[pd.DataFrame] = None,
    ) -> SignalDecision:
        """Combina sinal técnico + sentiment + filtro macro."""
        tech_signal = technical.signal
        sent_signal = sentiment.signal

        if sentiment.source.startswith("fallback"):
            logger.warning(
                f"[SignalCombiner] Sentiment usando FALLBACK (source='{sentiment.source}'). "
                f"Razão: {sentiment.reason}. "
                "O sinal será gerado com sentiment=neutral — qualidade reduzida."
            )

        if _is_suspicious_score(sentiment.score) and sent_signal != "neutral":
            logger.warning(
                f"[SignalCombiner] sentiment_score={sentiment.score} é exatamente 0.50 "
                f"para sinal '{sent_signal}'. Possível fallback estático no FinBERT."
            )

        final = self.DECISION_TABLE.get((tech_signal, sent_signal), AGUARDAR)

        if self.only_strong and final in (CALL_FRACO, PUT_FRACO):
            final = AGUARDAR

        # --- Filtro macro (#8 / fix #34) ---
        # macro_ok == False  → tendência desfavorável → bloquear
        # macro_ok == None   → mercado lateral ou dados insuficientes → bloquear conservadoramente
        # macro_ok == True   → tendência favorável → permitir
        macro_blocked = False
        if self.macro_filter is not None and final != AGUARDAR:
            direcao = "CALL" if final in (CALL_FORTE, CALL_FRACO) else "PUT"
            macro_ok = self.macro_filter.tendencia_favoravel(df_macro, direcao)
            if macro_ok is not True:
                motivo = (
                    "tendência desfavorável"
                    if macro_ok is False
                    else "mercado lateral / dados insuficientes"
                )
                logger.info(
                    f"[MacroFilter] {direcao} bloqueado — {motivo} "
                    f"(sinal original era '{final}')"
                )
                final = AGUARDAR
                macro_blocked = True

        confidence = self._calc_confidence(final, sentiment.score)
        reason = self._build_reason(final, technical, sentiment, macro_blocked)

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
            atr=technical.atr,
            current_price=technical.current_price,
            sentiment_score=sentiment.score,
            news_count=sentiment.news_count,
            sentiment_raw=sentiment.raw_scores,
            sentiment_source=sentiment.source,
            sentiment_reason=sentiment.reason,
            macro_blocked=macro_blocked,
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
        return round(min(0.50 + sentiment_score * 0.15, 0.75), 4)

    @staticmethod
    def _build_reason(
        final: str,
        tech: TechnicalResult,
        sent: SentimentResult,
        macro_blocked: bool = False,
    ) -> str:
        raw_str = (
            f"raw={sent.raw_scores}" if sent.raw_scores
            else f"raw=N/A source={sent.source}"
        )
        parts = [
            f"Técnico: {tech.signal} ({tech.reason})",
            f"Sentiment: {sent.signal} score={sent.score:.4f} {raw_str} | {sent.news_count} notícias | {sent.reason}",
            f"Decisão: {final}",
        ]
        if macro_blocked:
            parts.append("Macro: BLOQUEADO (tendência desfavorável no 1h)")
        return " || ".join(parts)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
    logging.basicConfig(level=logging.DEBUG)

    from backend.market.binance_client import BinanceClient
    from backend.analysis.technical import TechnicalAnalyzer
    from backend.analysis.sentiment import SentimentAnalyzer
    from backend.analysis.macro_filter import MacroTrendFilter
    from backend.market.symbols import SYMBOL_KEYWORDS

    SYMBOL = "BTCUSDT"
    bc = BinanceClient()
    df5m = bc.get_candles(symbol=SYMBOL, interval="5m", limit=100)
    df1h  = bc.get_candles(symbol=SYMBOL, interval="1h", limit=100)

    tech_analyzer = TechnicalAnalyzer()
    tech = tech_analyzer.analyze(df5m)
    sent_analyzer = SentimentAnalyzer(min_confidence=0.6)
    keyword = SYMBOL_KEYWORDS.get(SYMBOL, "bitcoin")
    sent = sent_analyzer.get_news_sentiment(keyword=keyword, news_limit=5)

    macro = MacroTrendFilter()
    combiner = SignalCombiner(symbol=SYMBOL, timeframe="5m", macro_filter=macro)
    decision = combiner.combine(tech, sent, df_macro=df1h)
    print(f"\n{decision.debug_breakdown()}")
