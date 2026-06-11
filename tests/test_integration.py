"""
tests/test_integration.py
Testes de integração ponta a ponta do Roboto.

Cobre o fluxo completo:
    TechnicalAnalyzer → SentimentAnalyzer → SignalCombiner → RiskManager
    e também o BacktestEngine como orquestrador desse pipeline.

Todos os testes rodam 100% offline (FinBERT e NewsAPI mockados via conftest.py).
"""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from datetime import date

from backend.analysis.technical import TechnicalAnalyzer
from backend.analysis.sentiment import SentimentAnalyzer, SentimentResult
from backend.analysis.signals import (
    SignalCombiner,
    CALL_FORTE, CALL_FRACO, PUT_FORTE, PUT_FRACO, AGUARDAR,
)
from backend.risk.manager import RiskManager
from backend.backtest.engine import BacktestEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_candles(n: int = 120, start: float = 50_000.0, step: float = 10.0) -> pd.DataFrame:
    """Gera DataFrame de candles sintéticos com open_time."""
    rows = []
    price = start
    ts = pd.Timestamp("2024-01-01")
    for _ in range(n):
        rows.append({
            "open_time": ts,
            "open":   price,
            "high":   price + 200,
            "low":    price - 200,
            "close":  price,
            "volume": 100.0,
        })
        price += step
        ts += pd.Timedelta(minutes=5)
    return pd.DataFrame(rows)


def make_sentiment(
    signal: str = "positive",
    score: float = 0.85,
    source: str = "finbert",
) -> SentimentResult:
    return SentimentResult(
        signal=signal,
        score=score,
        news_count=5,
        reason=f"mock-{signal}",
        source=source,
        raw_scores={"positive": 0.85, "negative": 0.10, "neutral": 0.05},
    )


# ---------------------------------------------------------------------------
# 1. TechnicalAnalyzer → produz TechnicalResult com ATR
# ---------------------------------------------------------------------------

class TestTechnicalIntegration:

    def test_analyze_retorna_sinal_valido(self):
        df = make_candles(n=120)
        result = TechnicalAnalyzer().analyze(df)
        assert result.signal in {"CALL", "PUT", "AGUARDAR"}

    def test_analyze_preenche_todos_indicadores(self):
        df = make_candles(n=120)
        result = TechnicalAnalyzer().analyze(df)
        assert result.rsi is not None
        assert result.ema50 is not None
        assert result.macd is not None
        assert result.bb_upper is not None
        assert result.bb_lower is not None
        assert result.current_price is not None

    def test_analyze_expoe_atr(self):
        df = make_candles(n=120)
        result = TechnicalAnalyzer(atr_period=14).analyze(df)
        assert result.atr is not None
        assert result.atr > 0

    def test_candles_insuficientes_retorna_aguardar(self):
        df = make_candles(n=30)
        result = TechnicalAnalyzer(min_candles=60).analyze(df)
        assert result.signal == "AGUARDAR"


# ---------------------------------------------------------------------------
# 2. SentimentAnalyzer → produz SentimentResult com source e raw_scores
# ---------------------------------------------------------------------------

class TestSentimentIntegration:

    def test_analyze_news_retorna_source_finbert(self):
        analyzer = SentimentAnalyzer()
        news = [{"title": "Bitcoin rallies", "description": "BTC up 5%"}]
        result = analyzer.analyze_news(news)
        # conftest mocka o pipeline com score positive=0.82 (maioria)
        assert result.signal in {"positive", "negative", "neutral"}
        assert result.source in {"finbert", "cache"}
        assert isinstance(result.raw_scores, dict)

    def test_analyze_news_lista_vazia_retorna_fallback(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_news([])
        assert result.signal == "neutral"
        assert result.source == "fallback_no_news"
        assert result.score == 0.0

    def test_analyze_news_textos_vazios_retorna_fallback(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_news([{"title": "", "description": ""}])
        assert result.source == "fallback_empty_texts"

    def test_analyze_news_popula_raw_scores(self):
        analyzer = SentimentAnalyzer()
        news = [
            {"title": "Bitcoin rallies", "description": "BTC up 5%"},
            {"title": "Crypto boom",     "description": "Record high"},
        ]
        result = analyzer.analyze_news(news)
        assert "positive" in result.raw_scores
        assert "negative" in result.raw_scores
        assert "neutral"  in result.raw_scores

    def test_get_news_sentiment_usa_newsapi_mockado(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.get_news_sentiment(keyword="bitcoin", page_size=5)
        # conftest mocka 2 artigos positivos
        assert result.signal in {"positive", "negative", "neutral"}
        assert result.news_count >= 0

    def test_cache_retorna_source_cache_na_segunda_chamada(self):
        analyzer = SentimentAnalyzer(cache_ttl=60)
        news = [{"title": "Bitcoin rallies", "description": "BTC up 5%"}]
        r1 = analyzer.analyze_news(news)
        r2 = analyzer.analyze_news(news)
        assert r2.source == "cache"


# ---------------------------------------------------------------------------
# 3. SignalCombiner — integração técnico + sentiment
# ---------------------------------------------------------------------------

class TestSignalCombinerIntegration:

    def test_call_forte_gera_campos_completos(self):
        df = make_candles(n=120, step=10.0)  # tendência de alta → favorece CALL
        tech = TechnicalAnalyzer().analyze(df)
        sent = make_sentiment("positive", score=0.85)
        combiner = SignalCombiner(symbol="BTCUSDT", timeframe="5m")
        decision = combiner.combine(tech, sent)

        assert decision.final in {CALL_FORTE, CALL_FRACO, PUT_FORTE, PUT_FRACO, AGUARDAR}
        assert decision.technical_signal in {"CALL", "PUT", "AGUARDAR"}
        assert decision.sentiment_signal == "positive"
        assert decision.sentiment_raw == sent.raw_scores
        assert decision.sentiment_source == "finbert"
        assert isinstance(decision.sentiment_reason, str)
        assert decision.confidence >= 0.0
        assert decision.timestamp != ""

    def test_decision_com_fallback_sinaliza_source_correto(self):
        df = make_candles(n=120)
        tech = TechnicalAnalyzer().analyze(df)
        sent = make_sentiment("neutral", score=0.0, source="fallback_newsapi_error")
        decision = SignalCombiner().combine(tech, sent)
        assert decision.sentiment_source == "fallback_newsapi_error"
        assert "FALLBACK" in decision.debug_breakdown()

    def test_debug_breakdown_contem_todos_campos(self):
        df = make_candles(n=120)
        tech = TechnicalAnalyzer().analyze(df)
        sent = make_sentiment("positive")
        decision = SignalCombiner(symbol="ETHUSDT", timeframe="15m").combine(tech, sent)
        bd = decision.debug_breakdown()
        for campo in ["RSI", "EMA50", "MACD", "Bollinger", "FinBERT raw",
                      "Sentiment", "Decisão", "ETHUSDT", "15m"]:
            assert campo in bd, f"Campo ausente no debug_breakdown: '{campo}'"

    def test_only_strong_bloqueia_sinais_fracos(self):
        df = make_candles(n=120)
        tech = TechnicalAnalyzer().analyze(df)
        sent = make_sentiment("neutral")  # resultaria em CALL_FRACO ou PUT_FRACO
        combiner = SignalCombiner(only_strong=True)
        decision = combiner.combine(tech, sent)
        assert decision.final not in {CALL_FRACO, PUT_FRACO}


# ---------------------------------------------------------------------------
# 4. RiskManager — integração com SignalDecision real
# ---------------------------------------------------------------------------

class TestRiskManagerIntegration:

    def _make_decision_from_pipeline(self, sentiment_signal="positive"):
        df = make_candles(n=120, step=10.0)
        tech = TechnicalAnalyzer().analyze(df)
        tech.atr = 150.0  # injeta ATR diretamente
        sent = make_sentiment(sentiment_signal)
        decision = SignalCombiner(symbol="BTCUSDT", timeframe="5m").combine(tech, sent)
        # garante current_price preenchido
        decision.current_price = decision.current_price or 50_000.0
        return decision

    def test_pct_stop_calculado_corretamente(self):
        rm = RiskManager(stop_loss_pct=5.0, take_profit_pct=10.0, use_atr_stop=False)
        decision = self._make_decision_from_pipeline()
        if not decision.is_actionable() or not decision.is_strong():
            pytest.skip("Sinal não acionável com dados sintéticos")
        trade = rm.open_trade(decision)
        price = trade.entry_price
        if trade.direction == "CALL":
            assert trade.stop_loss  == round(price * 0.95, 2)
            assert trade.take_profit == round(price * 1.10, 2)
        else:
            assert trade.stop_loss  == round(price * 1.05, 2)
            assert trade.take_profit == round(price * 0.90, 2)
        assert trade.stop_loss_mode == "pct"

    def test_atr_stop_calculado_corretamente(self):
        rm = RiskManager(use_atr_stop=True, atr_multiplier=2.0, stop_loss_pct=5.0)
        decision = self._make_decision_from_pipeline()
        if not decision.is_actionable() or not decision.is_strong():
            pytest.skip("Sinal não acionável com dados sintéticos")
        decision.atr = 150.0
        trade = rm.open_trade(decision)
        price = trade.entry_price
        if trade.direction == "CALL":
            assert trade.stop_loss == round(price - 150.0 * 2.0, 2)
        else:
            assert trade.stop_loss == round(price + 150.0 * 2.0, 2)
        assert trade.stop_loss_mode == "atr"
        assert trade.atr_at_entry == 150.0

    def test_trade_win_atualiza_saldo(self):
        rm = RiskManager(balance=10_000.0, stop_loss_pct=5.0, take_profit_pct=10.0)
        decision = self._make_decision_from_pipeline()
        if not decision.is_actionable() or not decision.is_strong():
            pytest.skip("Sinal não acionável com dados sintéticos")
        trade = rm.open_trade(decision)
        rm.close_trade(trade, trade.take_profit)
        assert trade.result == "WIN"
        assert rm.balance > 10_000.0

    def test_trade_loss_reduz_saldo(self):
        rm = RiskManager(balance=10_000.0, stop_loss_pct=5.0)
        decision = self._make_decision_from_pipeline()
        if not decision.is_actionable() or not decision.is_strong():
            pytest.skip("Sinal não acionável com dados sintéticos")
        trade = rm.open_trade(decision)
        rm.close_trade(trade, trade.stop_loss)
        assert trade.result == "LOSS"
        assert rm.balance < 10_000.0

    def test_drawdown_maximo_pausa_bot(self):
        rm = RiskManager(balance=10_000.0, max_drawdown_pct=10.0, stop_loss_pct=5.0)
        decision = self._make_decision_from_pipeline()
        if not decision.is_actionable() or not decision.is_strong():
            pytest.skip("Sinal não acionável com dados sintéticos")
        # força 3 losses seguidos para bater drawdown
        for _ in range(3):
            rm._open_trade = None
            rm._today_count = 0
            trade = rm.open_trade(decision)
            rm.close_trade(trade, trade.stop_loss)
            if rm.is_paused():
                break
        assert rm.is_paused()

    def test_limite_diario_bloqueia_novo_trade(self):
        rm = RiskManager(max_trades_day=2, only_strong=False)
        decision = self._make_decision_from_pipeline()
        decision.final = CALL_FORTE  # garante sinal acionável
        today = date.today()
        rm._open_trade = None; rm.open_trade(decision, current_date=today)
        rm._open_trade = None; rm.open_trade(decision, current_date=today)
        rm._open_trade = None
        ok, reason = rm.can_trade(decision, current_date=today)
        assert ok is False
        assert "Limite diário" in reason


# ---------------------------------------------------------------------------
# 5. BacktestEngine — pipeline completo sobre histórico sintético
# ---------------------------------------------------------------------------

class TestBacktestEngineIntegration:

    def test_backtest_call_forte_completa_sem_erro(self):
        df = make_candles(n=300, step=10.0)
        engine = BacktestEngine(
            symbol="BTCUSDT", interval="5m",
            balance=10_000.0, sentiment_mode="positive",
        )
        result = engine.run(df)
        assert result.symbol == "BTCUSDT"
        assert result.total_candles == 300
        assert result.initial_balance == 10_000.0
        assert isinstance(result.final_balance, float)
        assert result.total_signals >= 0

    def test_backtest_put_forte_completa_sem_erro(self):
        df = make_candles(n=300, step=-10.0)  # tendência de baixa
        engine = BacktestEngine(
            symbol="BTCUSDT", interval="5m",
            balance=10_000.0, sentiment_mode="negative",
        )
        result = engine.run(df)
        assert result.symbol == "BTCUSDT"
        assert isinstance(result.final_balance, float)

    def test_backtest_neutral_gera_apenas_aguardar(self):
        df = make_candles(n=300)
        engine = BacktestEngine(sentiment_mode="neutral", only_strong=True)
        result = engine.run(df)
        # Com sentiment neutral + only_strong, nenhum trade deve ser aberto
        assert result.total_trades == 0

    def test_backtest_sentiment_mode_invalido_levanta_erro(self):
        with pytest.raises(ValueError, match="sentiment_mode inválido"):
            BacktestEngine(sentiment_mode="bullish")

    def test_backtest_candles_insuficientes_levanta_erro(self):
        df = make_candles(n=30)
        engine = BacktestEngine()
        with pytest.raises(ValueError, match="DataFrame insuficiente"):
            engine.run(df)

    def test_backtest_equity_curve_preenchida(self):
        df = make_candles(n=300)
        result = BacktestEngine(sentiment_mode="positive").run(df)
        assert len(result.equity_curve) > 0
        ts, bal = result.equity_curve[0]
        assert isinstance(bal, float)

    def test_backtest_trades_sao_da_classe_trade(self):
        from backend.risk.manager import Trade
        df = make_candles(n=300, step=10.0)
        result = BacktestEngine(sentiment_mode="positive").run(df)
        for t in result.trades:
            assert isinstance(t, Trade)
            assert t.result in {"WIN", "LOSS"}

    def test_backtest_win_rate_entre_0_e_100(self):
        df = make_candles(n=300, step=10.0)
        result = BacktestEngine(sentiment_mode="positive").run(df)
        assert 0.0 <= result.win_rate <= 100.0

    def test_backtest_summary_contem_campos_chave(self):
        df = make_candles(n=300)
        result = BacktestEngine(sentiment_mode="positive").run(df)
        summary = result.summary()
        for campo in ["Backtest", "Trades", "Win Rate", "Drawdown", "PnL"]:
            assert campo in summary, f"Campo ausente no summary: '{campo}'"

    def test_backtest_sentiment_mock_expoe_source_backtest_mock(self):
        df = make_candles(n=300)
        engine = BacktestEngine(sentiment_mode="positive")
        # verifica que o sentiment interno usa source correto
        assert engine._sentiment.source == "backtest_mock"
        assert engine._sentiment.signal == "positive"
        assert engine._sentiment.raw_scores["positive"] == 0.85
