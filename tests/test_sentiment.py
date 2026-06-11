"""
tests/test_sentiment.py
Testes unitários do SentimentAnalyzer — foco em comportamento de fallback
e diagnóstico do FinBERT (issues #5 e #9).
Todos offline — FinBERT mockado via conftest.py.
"""

import pytest
from unittest.mock import patch
from backend.analysis.sentiment import SentimentAnalyzer, SentimentResult, _is_suspicious_score


@pytest.fixture
def analyzer():
    return SentimentAnalyzer(min_confidence=0.6, cache_ttl=0)


def _mock_pipeline(responses):
    iterator = iter(responses)
    def _call(text):
        return next(iterator)
    return _call


def test_is_suspicious_score_detecta_exatamente_0_5():
    assert _is_suspicious_score(0.5) is True
    assert _is_suspicious_score(0.50) is True


def test_is_suspicious_score_nao_dispara_para_outros_valores():
    assert _is_suspicious_score(0.51) is False
    assert _is_suspicious_score(0.49) is False
    assert _is_suspicious_score(0.82) is False
    assert _is_suspicious_score(0.0)  is False


def test_analyze_news_lista_vazia_retorna_neutral(analyzer):
    result = analyzer.analyze_news([])
    assert result.signal == "neutral"
    assert result.score == 0.0
    assert result.source == "fallback_no_news"
    assert result.raw_scores == {}


def test_analyze_news_textos_vazios_retorna_fallback(analyzer):
    news = [{"title": "", "description": ""}, {"title": "   "}]
    result = analyzer.analyze_news(news)
    assert result.signal == "neutral"
    assert result.source == "fallback_empty_texts"


def test_finbert_falha_ao_carregar_retorna_fallback(analyzer):
    with patch.object(analyzer, "_load_model", side_effect=RuntimeError("modelo não encontrado")):
        result = analyzer.analyze_news([{"title": "Bitcoin rallies"}])
    assert result.signal == "neutral"
    assert result.source == "fallback_finbert_error"
    assert result.raw_scores == {}


def test_finbert_retorna_positive(analyzer):
    raw_positive = [
        [{"label": "positive", "score": 0.91}, {"label": "negative", "score": 0.05}, {"label": "neutral", "score": 0.04}],
        [{"label": "positive", "score": 0.88}, {"label": "negative", "score": 0.07}, {"label": "neutral", "score": 0.05}],
    ]
    with patch.object(analyzer, "_load_model"):
        analyzer._pipeline = _mock_pipeline(raw_positive)
        result = analyzer.analyze_news([
            {"title": "Bitcoin surges to all-time high"},
            {"title": "Institutional demand drives crypto rally"},
        ])
    assert result.signal == "positive"
    assert result.score > 0.5
    assert result.source == "finbert"
    assert "positive" in result.raw_scores
    assert result.raw_scores["positive"] > result.raw_scores["negative"]


def test_finbert_retorna_negative(analyzer):
    raw_negative = [
        [{"label": "negative", "score": 0.93}, {"label": "positive", "score": 0.04}, {"label": "neutral", "score": 0.03}],
        [{"label": "negative", "score": 0.87}, {"label": "positive", "score": 0.08}, {"label": "neutral", "score": 0.05}],
    ]
    with patch.object(analyzer, "_load_model"):
        analyzer._pipeline = _mock_pipeline(raw_negative)
        result = analyzer.analyze_news([
            {"title": "Bitcoin crashes 30%, panic selling spreads"},
            {"title": "Regulatory crackdown sends crypto tumbling"},
        ])
    assert result.signal == "negative"
    assert result.score > 0.5
    assert result.source == "finbert"
    assert result.raw_scores["negative"] > result.raw_scores["positive"]


def test_finbert_score_nao_e_sempre_0_5(analyzer):
    raw = [
        [{"label": "positive", "score": 0.85}, {"label": "negative", "score": 0.10}, {"label": "neutral", "score": 0.05}],
    ]
    with patch.object(analyzer, "_load_model"):
        analyzer._pipeline = _mock_pipeline(raw)
        result = analyzer.analyze_news([{"title": "Bitcoin hits new ATH"}])
    assert not _is_suspicious_score(result.score)


def test_finbert_simetria_positive_vs_negative(analyzer):
    raw_pos = [[{"label": "positive", "score": 0.90}, {"label": "negative", "score": 0.06}, {"label": "neutral", "score": 0.04}]]
    raw_neg = [[{"label": "negative", "score": 0.90}, {"label": "positive", "score": 0.06}, {"label": "neutral", "score": 0.04}]]
    with patch.object(analyzer, "_load_model"):
        analyzer._pipeline = _mock_pipeline(raw_pos)
        r_pos = analyzer.analyze_news([{"title": "Bitcoin surges to all-time high"}])
        analyzer._pipeline = _mock_pipeline(raw_neg)
        r_neg = analyzer.analyze_news([{"title": "Bitcoin crashes, markets panic"}])
    assert r_pos.signal == "positive"
    assert r_neg.signal == "negative"


def test_score_abaixo_do_threshold_vira_neutral(analyzer):
    raw = [[{"label": "positive", "score": 0.55}, {"label": "negative", "score": 0.25}, {"label": "neutral", "score": 0.20}]]
    with patch.object(analyzer, "_load_model"):
        analyzer._pipeline = _mock_pipeline(raw)
        result = analyzer.analyze_news([{"title": "Bitcoin maybe going up"}])
    assert result.signal == "neutral"
