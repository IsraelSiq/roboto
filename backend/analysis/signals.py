"""
Roboto — Núcleo de Sinais ⭐
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

Uso:
    from backend.analysis.signals import SignalCombiner
    combiner = SignalCombiner()
    decision = combiner.combine(technical_result, sentiment_result)
    print(decision.final)   # CALL_FORTE | PUT_FORTE | CALL_FRACO | PUT_FRACO | AGUARDAR
    print(decision.reason)  # explicação completa
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

from backend.analysis.technical import TechnicalResult
from backend.analysis.sentiment import SentimentResult
from backend.market.symbols import SYMBOL_KEYWORDS

load_dotenv()
logger = logging.getLogger(__name__)

# Decisões possíveis
CALL_FORTE  = "CALL_FORTE"
CALL_FRACO  = "CALL_FRACO"
PUT_FORTE   = "PUT_FORTE"
PUT_FRACO   = "PUT_FRACO"
AGUARDAR    = "AGUARDAR"


@dataclass
class SignalDecision:
    """Decisão final combinada do robô."""
    final: str                        # CALL_FORTE | PUT_FORTE | CALL_FRACO | PUT_FRACO | AGUARDAR
    technical_signal: str             # CALL | PUT | AGUARDAR
    sentiment_signal: str             # positive | negative | neutral
    reason: str                       # explicação completa
    confidence: float                 # 0.0 – 1.0 (combina técnico + sentiment)
    symbol: str = "BTCUSDT"
    timeframe: str = "5m"
    timestamp: str = ""

    # Métricas técnicas (para log no Supabase)
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    ema50: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    current_price: Optional[float] = None
    sentiment_score: Optional[float] = None
    news_count: int = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def is_actionable(self) -> bool:
        """Retorna True se a decisão é acionável (não é AGUARDAR)."""
        return self.final != AGUARDAR

    def is_strong(self) -> bool:
        """Retorna True se é um sinal forte."""
        return self.final in (CALL_FORTE, PUT_FORTE)

    def direction(self) -> str:
        """Retorna a direção: CALL | PUT | AGUARDAR."""
        if self.final in (CALL_FORTE, CALL_FRACO):
            return "CALL"
        if self.final in (PUT_FORTE, PUT_FRACO):
            return "PUT"
        return "AGUARDAR"

    def strength(self) -> str:
        """Retorna a força: FORTE | FRACO | -."""
        if self.final in (CALL_FORTE, PUT_FORTE):
            return "FORTE"
        if self.final in (CALL_FRACO, PUT_FRACO):
            return "FRACO"
        return "-"

    def summary(self) -> str:
        """Resumo formatado para log."""
        emoji = {
            CALL_FORTE: "✅ CALL FORTE",
            CALL_FRACO: "⚠️ CALL FRACO",
            PUT_FORTE:  "✅ PUT FORTE",
            PUT_FRACO:  "⚠️ PUT FRACO",
            AGUARDAR:   "⏸️ AGUARDAR",
        }
        return (
            f"{emoji.get(self.final, self.final)} | "
            f"Preço: ${self.current_price:,.2f} | "
            f"RSI: {self.rsi} | "
            f"Sentiment: {self.sentiment_signal} ({self.sentiment_score:.2f}) | "
            f"Confiança: {self.confidence:.0%}"
        )


class SignalCombiner:
    """
    Núcleo do robô — combina sinal técnico + sentiment.

    Args:
        symbol:    Par de trading (ex: 'BTCUSDT')
        timeframe: Timeframe (ex: '5m')
        only_strong: Se True, só retorna CALL_FORTE e PUT_FORTE (ignora sinais fracos)
    """

    DECISION_TABLE = {
        ("CALL", "positive"): CALL_FORTE,
        ("CALL", "neutral"):  CALL_FRACO,
        ("CALL", "negative"): AGUARDAR,
        ("PUT",  "negative"): PUT_FORTE,
        ("PUT",  "neutral"):  PUT_FRACO,
        ("PUT",  "positive"): AGUARDAR,
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
            SignalDecision com decisão final, confiança e todos os detalhes
        """
        tech_signal = technical.signal          # CALL | PUT | AGUARDAR
        sent_signal = sentiment.signal          # positive | negative | neutral

        # Lookup na tabela de decisão
        final = self.DECISION_TABLE.get((tech_signal, sent_signal), AGUARDAR)

        # Se only_strong, rebaixa sinais fracos para AGUARDAR
        if self.only_strong and final in (CALL_FRACO, PUT_FRACO):
            final = AGUARDAR

        # Calcula confiança: média ponderada entre técnico e sentiment
        confidence = self._calc_confidence(final, sentiment.score)

        # Monta reason completo
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
        )

        logger.info(f"[Signal] {decision.summary()}")
        return decision

    # ----------------------------------------------------------
    # HELPERS
    # ----------------------------------------------------------

    @staticmethod
    def _calc_confidence(final: str, sentiment_score: float) -> float:
        """
        Calcula confiança da decisão:
            FORTE  → base 0.75 + boost do sentiment_score
            FRACO  → base 0.50 + boost reduzido
            AGUARDAR → 0.0
        """
        if final == AGUARDAR:
            return 0.0
        if final in (CALL_FORTE, PUT_FORTE):
            return round(min(0.75 + sentiment_score * 0.25, 1.0), 4)
        # FRACO
        return round(min(0.50 + sentiment_score * 0.15, 0.75), 4)

    @staticmethod
    def _build_reason(final: str, tech: TechnicalResult, sent: SentimentResult) -> str:
        """Monta string de reason completo para log e debug."""
        parts = [
            f"Técnico: {tech.signal} ({tech.reason})",
            f"Sentiment: {sent.signal} | score={sent.score:.2f} | {sent.news_count} notícias ({sent.reason})",
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
    logging.basicConfig(level=logging.INFO)

    from backend.market.binance_client import BinanceClient
    from backend.analysis.technical import TechnicalAnalyzer
    from backend.analysis.sentiment import SentimentAnalyzer
    from backend.market.symbols import SYMBOL_KEYWORDS

    SYMBOL = "BTCUSDT"

    print(f"\n{'='*55}")
    print(f"  Roboto — Ciclo completo de sinal ({SYMBOL})")
    print(f"{'='*55}")

    # 1. Coleta candles
    print("\n[1/3] Coletando candles...")
    bc = BinanceClient()
    df = bc.get_candles(symbol=SYMBOL, interval="5m", limit=100)
    print(f"  {len(df)} candles recebidos")

    # 2. Análise técnica
    print("\n[2/3] Análise técnica...")
    tech_analyzer = TechnicalAnalyzer()
    tech = tech_analyzer.analyze(df)
    print(f"  Sinal técnico : {tech.signal}")
    print(f"  RSI           : {tech.rsi}")
    print(f"  MACD cross    : {tech.macd_cross}")
    print(f"  Preço vs EMA  : {tech.price_vs_ema}")

    # 3. Sentiment
    print("\n[3/3] Sentiment analysis...")
    sent_analyzer = SentimentAnalyzer(min_confidence=0.6)
    keyword = SYMBOL_KEYWORDS.get(SYMBOL, "bitcoin")
    sent = sent_analyzer.get_news_sentiment(keyword=keyword, page_size=5)
    print(f"  Sinal sentiment: {sent.signal} (score={sent.score})")
    print(f"  Notícias       : {sent.news_count}")

    # 4. Combinação final
    print(f"\n{'='*55}")
    combiner = SignalCombiner(symbol=SYMBOL, timeframe="5m")
    decision = combiner.combine(tech, sent)

    print(f"\n  {decision.summary()}")
    print(f"\n  Decisão final : {decision.final}")
    print(f"  Direção       : {decision.direction()}")
    print(f"  Força         : {decision.strength()}")
    print(f"  Confiança     : {decision.confidence:.0%}")
    print(f"  Acionável     : {decision.is_actionable()}")
    print(f"\n  Reason:\n    {decision.reason}")
    print(f"\n{'='*55}")

    # 5. Teste com todos os cenários da tabela de decisão
    print("\n[EXTRA] Tabela de decisão completa:")
    from backend.analysis.technical import TechnicalResult
    from backend.analysis.sentiment import SentimentResult

    scenarios = [
        ("CALL",    "positive"),
        ("CALL",    "neutral"),
        ("CALL",    "negative"),
        ("PUT",     "negative"),
        ("PUT",     "neutral"),
        ("PUT",     "positive"),
        ("AGUARDAR","positive"),
        ("AGUARDAR","neutral"),
        ("AGUARDAR","negative"),
    ]

    print(f"  {'Técnico':<12} {'Sentiment':<12} {'Decisão':<15}")
    print(f"  {'-'*40}")
    for tech_s, sent_s in scenarios:
        mock_tech = TechnicalResult(signal=tech_s, reason="mock", rsi=50.0, current_price=60000.0, ema50=59000.0)
        mock_sent = SentimentResult(signal=sent_s, score=0.85, news_count=5, reason="mock")
        d = combiner.combine(mock_tech, mock_sent)
        print(f"  {tech_s:<12} {sent_s:<12} {d.final:<15}")
