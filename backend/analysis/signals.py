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
    print(decision.final)           # CALL_FORTE | PUT_FORTE | CALL_FRACO | PUT_FRACO | AGUARDAR
    print(decision.sentiment_raw)   # {'positive': 0.82, 'negative': 0.10, 'neutral': 0.08}
    print(decision.sentiment_source)  # 'finbert' | 'fallback_newsapi_error' | ...
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

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

    # --- Campos novos para diagnóstico (#9 + #5) ---
    sentiment_raw: dict = field(default_factory=dict)
    # ex: {'positive': 0.82, 'negative': 0.10, 'neutral': 0.08}

    sentiment_source: str = "finbert"
    # 'finbert' | 'cache' | 'fallback_no_news' | 'fallback_newsapi_error' |
    # 'fallback_finbert_error' | 'fallback_empty_texts'

    sentiment_reason: str = ""
    # Razão detalhada do sentiment (ex: "NewsAPI falhou", "3/5 notícias negativas")

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
        return (
            f"{emoji.get(self.final, self.final)} | "
            f"Preço: ${self.current_price:,.2f} | "
            f"RSI: {self.rsi} | "
            f"Sentiment: {self.sentiment_signal} ({score_str}) | "
            f"Confiança: {self.confidence:.0%}"
        )

    def debug_breakdown(self) -> str:
        """Breakdown detalhado para log DEBUG — expõe cada componente individualmente."""
        raw_str = (
            f"pos={self.sentiment_raw.get('positive', '?'):.3f} "
            f"neg={self.sentiment_raw.get('negative', '?'):.3f} "
            f"neu={self.sentiment_raw.get('neutral', '?'):.3f}"
        ) if self.sentiment_raw else "(não disponível)"

        source_flag = ""
        if self.sentiment_source.startswith("fallback"):
            source_flag = " ⚠️ FALLBACK"

        lines = [
            f"┌─ SignalCombiner Breakdown ── {self.symbol} {self.timeframe} ──────────────────",
            f"│  Preço atual    : ${self.current_price:,.2f}",
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
            f"│  Confiança final: {self.confidence:.0%}",
            f"└─ Decisão        : {self.final} ────────────────────────────────────────────",
        ]
        return "\n".join(lines)


class SignalCombiner:
    """
    Núcleo do robô — combina sinal técnico + sentiment.

    Args:
        symbol:      Par de trading (ex: 'BTCUSDT')
        timeframe:   Timeframe (ex: '5m')
        only_strong: Se True, só retorna CALL_FORTE e PUT_FORTE (ignora sinais fracos)
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
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.only_strong = only_strong

    # ----------------------------------------------------------
    # MÉTODO PRINCIPAL
    # ----------------------------------------------------------

    def combine(
        self,
        technical: TechnicalResult,
        sentiment: SentimentResult,
    ) -> SignalDecision:
        """
        Combina sinal técnico + sentiment e retorna a decisão final.

        Args:
            technical: Resultado da análise técnica (TechnicalResult)
            sentiment: Resultado da análise de sentiment (SentimentResult)

        Returns:
            SignalDecision com decisão final, confiança, breakdown e diagnóstico
        """
        tech_signal = technical.signal
        sent_signal = sentiment.signal

        # --- Alertas de diagnóstico (#5) ---
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

        # Lookup na tabela de decisão
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
            # --- Campos novos ---
            sentiment_raw=sentiment.raw_scores,
            sentiment_source=sentiment.source,
            sentiment_reason=sentiment.reason,
        )

        # Log INFO (formato original — compatível com parsers)
        logger.info(f"[Signal] {decision.summary()}")
        # Log DEBUG (breakdown completo por componente)
        logger.debug(decision.debug_breakdown())

        return decision

    # ----------------------------------------------------------
    # HELPERS
    # ----------------------------------------------------------

    @staticmethod
    def _calc_confidence(final: str, sentiment_score: float) -> float:
        if final == AGUARDAR:
            return 0.0
        if final in (CALL_FORTE, PUT_FORTE):
            return round(min(0.75 + sentiment_score * 0.25, 1.0), 4)
        return round(min(0.50 + sentiment_score * 0.15, 0.75), 4)

    @staticmethod
    def _build_reason(final: str, tech: TechnicalResult, sent: SentimentResult) -> str:
        raw_str = (
            f"raw={sent.raw_scores}" if sent.raw_scores
            else f"raw=N/A source={sent.source}"
        )
        parts = [
            f"Técnico: {tech.signal} ({tech.reason})",
            f"Sentiment: {sent.signal} score={sent.score:.4f} {raw_str} | {sent.news_count} notícias | {sent.reason}",
            f"Decisão: {final}",
        ]
        return " || ".join(parts)


# ----------------------------------------------------------
# Teste rápido
# ----------------------------------------------------------
if __name__ == "__main__":
    import logging
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
    logging.basicConfig(level=logging.DEBUG)

    from backend.market.binance_client import BinanceClient
    from backend.analysis.technical import TechnicalAnalyzer
    from backend.analysis.sentiment import SentimentAnalyzer
    from backend.market.symbols import SYMBOL_KEYWORDS

    SYMBOL = "BTCUSDT"

    print(f"\n{'='*60}")
    print(f"  Roboto — Ciclo completo de sinal ({SYMBOL})")
    print(f"{'='*60}")

    print("\n[1/3] Coletando candles...")
    bc = BinanceClient()
    df = bc.get_candles(symbol=SYMBOL, interval="5m", limit=100)
    print(f"  {len(df)} candles recebidos")

    print("\n[2/3] Análise técnica...")
    tech_analyzer = TechnicalAnalyzer()
    tech = tech_analyzer.analyze(df)
    print(f"  Sinal técnico : {tech.signal}")
    print(f"  RSI           : {tech.rsi}")

    print("\n[3/3] Sentiment analysis...")
    sent_analyzer = SentimentAnalyzer(min_confidence=0.6)
    keyword = SYMBOL_KEYWORDS.get(SYMBOL, "bitcoin")
    sent = sent_analyzer.get_news_sentiment(keyword=keyword, page_size=5)
    print(f"  Sinal         : {sent.signal} (score={sent.score})")
    print(f"  Source        : {sent.source}")
    print(f"  Raw scores    : {sent.raw_scores}")
    print(f"  Razão         : {sent.reason}")

    print(f"\n{'='*60}")
    combiner = SignalCombiner(symbol=SYMBOL, timeframe="5m")
    decision = combiner.combine(tech, sent)

    print(f"\n{decision.debug_breakdown()}")
    print(f"\n  Acionável     : {decision.is_actionable()}")
    print(f"  Forte         : {decision.is_strong()}")
    print(f"{'='*60}")

    # Tabela de decisão com todos os cenários
    print("\n[EXTRA] Tabela de decisão completa:")
    from backend.analysis.technical import TechnicalResult
    from backend.analysis.sentiment import SentimentResult

    scenarios = [
        ("CALL", "positive", {"positive": 0.90, "negative": 0.05, "neutral": 0.05}),
        ("CALL", "neutral", {"positive": 0.40, "negative": 0.20, "neutral": 0.40}),
        ("CALL", "negative", {"positive": 0.05, "negative": 0.90, "neutral": 0.05}),
        ("PUT", "negative", {"positive": 0.05, "negative": 0.90, "neutral": 0.05}),
        ("PUT", "neutral", {"positive": 0.20, "negative": 0.40, "neutral": 0.40}),
        ("PUT", "positive", {"positive": 0.90, "negative": 0.05, "neutral": 0.05}),
        ("AGUARDAR", "positive", {}),
    ]

    print(f"  {'Técnico':<12} {'Sentiment':<12} {'Source':<22} {'Decisão':<15} {'Confiança'}")
    print(f"  {'-'*75}")
    for tech_s, sent_s, raw in scenarios:
        mock_tech = TechnicalResult(
            signal=tech_s, reason="mock", rsi=50.0, current_price=90000.0, ema50=89000.0
        )
        mock_sent = SentimentResult(
            signal=sent_s, score=0.85, news_count=5, reason="mock", source="finbert", raw_scores=raw
        )
        d = combiner.combine(mock_tech, mock_sent)
        print(f"  {tech_s:<12} {sent_s:<12} {mock_sent.source:<22} {d.final:<15} {d.confidence:.0%}")
