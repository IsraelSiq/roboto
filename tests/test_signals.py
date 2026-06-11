"""
tests/test_signals.py
Testes unitários do SignalCombiner — tabela de decisão,
breakdown de scores e diagnóstico de fallback (issues #9 e #5).
"""

import pytest
import logging
from backend.analysis.signals import (
    SignalCombiner,
    SignalDecision,
    CALL_FORTE, CALL_FRACO, PUT_FORTE, PUT_FRACO, AGUARDAR,
)
from backend.analysis.technical import TechnicalResult
from backend.analysis.sentiment import SentimentResult


def make_tech(signal: str, rsi: float = 55.0, price: float = 90000.0) -> TechnicalResult:
    return TechnicalResult(
        signal=signal,
        reason=f"mock-{signal}",
        rsi=rsi,
        current_price=price,
        ema50=89000.0,
        macd=10.0,
        macd_signal=8.0,
        bb_upper=92000.0,
        bb_lower=88000.0,
    )


def make_sent(
    signal: str,
    score: float = 0.85,
    raw: dict = None,
    source: str = "finbert",
) -> SentimentResult:
    return SentimentResult(
        signal=signal,
        score=score,
        news_count=5,
        reason=f"mock-{signal}",
        source=source,
        raw_scores=raw or {"positive": 0.85, "negative": 0.10, "neutral": 0.05},
    )


@pytest.fixture
def combiner():
    return SignalCombiner(symbol="BTCUSDT", timeframe="5m")


@pytest.mark.parametrize("tech,sent,expected", [
    ("CALL",     "positive", CALL_FORTE),
    ("CALL",     "neutral",  CALL_FRACO),
    ("CALL",     "negative", AGUARDAR),
    ("PUT",      "negative", PUT_FORTE),
    ("PUT",      "neutral",  PUT_FRACO),
    ("PUT",      "positive", AGUARDAR),
    ("AGUARDAR", "positive", AGUARDAR),
    ("AGUARDAR", "neutral",  AGUARDAR),
    ("AGUARDAR", "negative", AGUARDAR),
])
def test_tabela_decisao_completa(combiner, tech, sent, expected):
    d = combiner.combine(make_tech(tech), make_sent(sent))
    assert d.final == expected


def test_confianca_call_forte_maior_que_call_fraco(combiner):
    d_forte = combiner.combine(make_tech("CALL"), make_sent("positive", score=0.90))
    d_fraco = combiner.combine(make_tech("CALL"), make_sent("neutral",  score=0.90))
    assert d_forte.confidence > d_fraco.confidence


def test_confianca_aguardar_e_zero(combiner):
    d = combiner.combine(make_tech("AGUARDAR"), make_sent("positive"))
    assert d.confidence == 0.0


def test_confianca_maximo_1_0(combiner):
    d = combiner.combine(make_tech("CALL"), make_sent("positive", score=1.0))
    assert d.confidence <= 1.0


def test_decision_expoe_sentiment_raw(combiner):
    raw = {"positive": 0.82, "negative": 0.10, "neutral": 0.08}
    d = combiner.combine(make_tech("CALL"), make_sent("positive", raw=raw))
    assert d.sentiment_raw == raw


def test_decision_expoe_sentiment_source(combiner):
    d = combiner.combine(make_tech("CALL"), make_sent("positive", source="finbert"))
    assert d.sentiment_source == "finbert"


def test_decision_expoe_sentiment_source_fallback(combiner):
    d = combiner.combine(make_tech("CALL"), make_sent("neutral", source="fallback_newsapi_error"))
    assert d.sentiment_source == "fallback_newsapi_error"


def test_decision_expoe_sentiment_reason(combiner):
    sent = make_sent("positive")
    sent.reason = "3/5 notícias positivas (score médio: 0.8700)"
    d = combiner.combine(make_tech("CALL"), sent)
    assert "3/5" in d.sentiment_reason


def test_debug_breakdown_contem_componentes(combiner):
    d = combiner.combine(make_tech("CALL"), make_sent("positive"))
    breakdown = d.debug_breakdown()
    assert "RSI" in breakdown
    assert "EMA50" in breakdown
    assert "MACD" in breakdown
    assert "FinBERT raw" in breakdown
    assert "Sentiment" in breakdown
    assert "Decisão" in breakdown


def test_debug_breakdown_sinaliza_fallback(combiner):
    d = combiner.combine(make_tech("CALL"), make_sent("neutral", source="fallback_newsapi_error"))
    breakdown = d.debug_breakdown()
    assert "FALLBACK" in breakdown


def test_debug_breakdown_sem_fallback_quando_finbert_ok(combiner):
    d = combiner.combine(make_tech("CALL"), make_sent("positive", source="finbert"))
    breakdown = d.debug_breakdown()
    assert "FALLBACK" not in breakdown


def test_warning_emitido_quando_source_e_fallback(combiner, caplog):
    with caplog.at_level(logging.WARNING, logger="backend.analysis.signals"):
        combiner.combine(
            make_tech("CALL"),
            make_sent("neutral", source="fallback_newsapi_error", score=0.0),
        )
    assert any("FALLBACK" in r.message for r in caplog.records)


def test_sem_warning_quando_source_e_finbert(combiner, caplog):
    with caplog.at_level(logging.WARNING, logger="backend.analysis.signals"):
        combiner.combine(
            make_tech("CALL"),
            make_sent("positive", source="finbert", score=0.85),
        )
    assert not any("FALLBACK" in r.message for r in caplog.records)


def test_only_strong_rebaixa_call_fraco(combiner):
    combiner.only_strong = True
    d = combiner.combine(make_tech("CALL"), make_sent("neutral"))
    assert d.final == AGUARDAR


def test_only_strong_mantem_call_forte(combiner):
    combiner.only_strong = True
    d = combiner.combine(make_tech("CALL"), make_sent("positive"))
    assert d.final == CALL_FORTE


def test_only_strong_mantem_put_forte(combiner):
    combiner.only_strong = True
    d = combiner.combine(make_tech("PUT"), make_sent("negative"))
    assert d.final == PUT_FORTE
