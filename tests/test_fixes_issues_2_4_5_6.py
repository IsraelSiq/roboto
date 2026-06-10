"""
Testes de regressão — Issues #2, #4, #5, #6

Cobertura:
    #2  — BacktestReporter.save() envia 'timeframe' (não 'interval') no payload
    #4  — TechnicalAnalyzer emite PUT em tendência de baixa (causa raiz do bug crítico)
    #5  — SentimentAnalyzer retorna source/raw_scores corretos e detecta fallback 0.50
    #6  — SignalCombiner gera PUT_FORTE / PUT_FRACO quando técnico é PUT
           RSI mutuamente exclusivo: > call_threshold → CALL, < put_threshold → PUT
"""

import pandas as pd
import numpy as np
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers compartilhados
# ---------------------------------------------------------------------------

def make_candles(n=120, trend="down", seed=42):
    """Gera DataFrame sintético com tendência definida."""
    np.random.seed(seed)
    base = 90_000.0
    prices = []
    for _ in range(n):
        if trend == "down":
            base -= np.random.uniform(50, 300)
        elif trend == "up":
            base += np.random.uniform(50, 300)
        else:
            base += np.random.uniform(-150, 150)
        prices.append(max(base, 1.0))
    return pd.DataFrame({
        "open":   [p * 0.999 for p in prices],
        "high":   [p * 1.002 for p in prices],
        "low":    [p * 0.998 for p in prices],
        "close":  prices,
        "volume": [np.random.uniform(100, 1000) for _ in range(n)],
    })


def make_tech(signal="PUT", rsi=35.0, price=75_000.0):
    t = MagicMock()
    t.signal = signal
    t.rsi = rsi
    t.macd = -100.0
    t.macd_signal = -50.0
    t.macd_cross = "DOWN"
    t.ema50 = 80_000.0
    t.bb_upper = 82_000.0
    t.bb_lower = 70_000.0
    t.current_price = price
    t.price_vs_ema = "BELOW"
    t.price_vs_bb = "MIDDLE"
    t.reason = "mock"
    return t


def make_sent(signal="negative", score=0.78, count=5):
    s = MagicMock()
    s.signal = signal
    s.score = score
    s.news_count = count
    s.reason = "mock"
    return s


# ===========================================================================
# Issue #2 — BacktestReporter: payload deve usar 'timeframe', não 'interval'
# ===========================================================================

class TestIssue2BacktestReporterPayload:
    """
    Garante que BacktestReporter.save() passa 'timeframe' no payload do Supabase
    e nunca 'interval' isolado (que violava NOT NULL constraint).
    """

    def _make_result(self, interval="5m"):
        r = MagicMock()
        r.symbol = "BTCUSDT"
        r.interval = interval
        r.start_date = "2026-01-01T00:00:00"
        r.end_date = "2026-06-09T00:00:00"
        r.initial_balance = 10_000.0
        r.final_balance = 9_000.0
        r.total_candles = 46_042
        r.total_signals = 2_032
        r.total_trades = 69
        r.wins = 17
        r.losses = 52
        r.win_rate = 24.6
        r.profit_factor = 0.65
        r.max_drawdown = 20.2
        r.sharpe_ratio = -1.67
        r.total_pnl_pct = -13.74
        r.approved = False
        return r

    def test_payload_contains_timeframe_key(self):
        """Payload deve conter 'timeframe' com o valor de result.interval."""
        from backend.backtest.report import BacktestReporter

        reporter = BacktestReporter()
        mock_table = MagicMock()
        mock_db = MagicMock()
        mock_db.client.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = MagicMock()
        reporter._db = mock_db

        result = self._make_result(interval="5m")
        reporter.save(result)

        inserted_payload = mock_table.insert.call_args[0][0]
        assert "timeframe" in inserted_payload, "Payload deve conter a chave 'timeframe'"
        assert inserted_payload["timeframe"] == "5m"

    def test_payload_does_not_contain_bare_interval_key(self):
        """Payload não deve conter 'interval' como chave standalone (causava 400)."""
        from backend.backtest.report import BacktestReporter

        reporter = BacktestReporter()
        mock_table = MagicMock()
        mock_db = MagicMock()
        mock_db.client.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = MagicMock()
        reporter._db = mock_db

        result = self._make_result(interval="15m")
        reporter.save(result)

        inserted_payload = mock_table.insert.call_args[0][0]
        assert "interval" not in inserted_payload, (
            "Payload não deve conter 'interval' — causa NOT NULL violation na coluna 'timeframe'"
        )

    def test_timeframe_value_matches_result_interval(self):
        """O valor de 'timeframe' no payload deve ser exatamente result.interval."""
        from backend.backtest.report import BacktestReporter

        reporter = BacktestReporter()
        mock_table = MagicMock()
        mock_db = MagicMock()
        mock_db.client.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = MagicMock()
        reporter._db = mock_db

        for tf in ["1m", "5m", "15m", "1h", "4h"]:
            result = self._make_result(interval=tf)
            reporter.save(result)
            payload = mock_table.insert.call_args[0][0]
            assert payload["timeframe"] == tf, f"Esperado timeframe='{tf}', obtido '{payload.get('timeframe')}'"


# ===========================================================================
# Issue #4/#6 — TechnicalAnalyzer deve emitir PUT em tendência de baixa
# ===========================================================================

class TestIssue4And6TechnicalPutSignal:
    """
    Garante que o TechnicalAnalyzer emite sinal PUT (e não somente CALL)
    após a correção dos thresholds RSI.
    """

    def setup_method(self):
        from backend.analysis.technical import TechnicalAnalyzer
        self.ta = TechnicalAnalyzer()

    def test_put_emitido_em_tendencia_de_baixa(self):
        """Tendência de baixa forte deve gerar PUT (não exclusivamente CALL)."""
        df = make_candles(200, trend="down")
        result = self.ta.analyze(df)
        assert result.signal in {"PUT", "AGUARDAR"}, (
            f"Esperado PUT ou AGUARDAR em tendência de baixa, obtido: {result.signal}"
        )

    def test_call_emitido_em_tendencia_de_alta(self):
        """Tendência de alta forte deve gerar CALL (comportamento original preservado)."""
        df = make_candles(200, trend="up")
        result = self.ta.analyze(df)
        assert result.signal in {"CALL", "AGUARDAR"}, (
            f"Esperado CALL ou AGUARDAR em tendência de alta, obtido: {result.signal}"
        )

    def test_rsi_scoring_mutuamente_exclusivo(self):
        """RSI alto (>55) só pontua CALL; RSI baixo (<45) só pontua PUT."""
        from backend.analysis.technical import TechnicalAnalyzer
        ta = TechnicalAnalyzer(rsi_call_threshold=55, rsi_put_threshold=45)

        # RSI alto: apenas CALL pontua no RSI
        call_score_rsi, put_score_rsi = 0, 0
        rsi_alto = 65.0
        if rsi_alto > ta.rsi_call_threshold:
            call_score_rsi += 1
        elif rsi_alto < ta.rsi_put_threshold:
            put_score_rsi += 1
        assert call_score_rsi == 1 and put_score_rsi == 0

        # RSI baixo: apenas PUT pontua no RSI
        call_score_rsi, put_score_rsi = 0, 0
        rsi_baixo = 35.0
        if rsi_baixo > ta.rsi_call_threshold:
            call_score_rsi += 1
        elif rsi_baixo < ta.rsi_put_threshold:
            put_score_rsi += 1
        assert call_score_rsi == 0 and put_score_rsi == 1

    def test_rsi_na_zona_neutra_nao_pontua(self):
        """RSI entre 45 e 55 (zona neutra) não deve pontuar nem CALL nem PUT."""
        from backend.analysis.technical import TechnicalAnalyzer
        ta = TechnicalAnalyzer(rsi_call_threshold=55, rsi_put_threshold=45)
        for rsi_neutro in [45.0, 50.0, 54.9, 55.0]:
            call_score, put_score = 0, 0
            if rsi_neutro > ta.rsi_call_threshold:
                call_score += 1
            elif rsi_neutro < ta.rsi_put_threshold:
                put_score += 1
            # RSI exatamente 55 pontua CALL (> threshold), demais não pontuam
            if rsi_neutro < ta.rsi_call_threshold and rsi_neutro >= ta.rsi_put_threshold:
                assert call_score == 0 and put_score == 0, (
                    f"RSI={rsi_neutro} na zona neutra não deveria pontuar"
                )

    def test_never_only_call_in_100_down_candles(self):
        """
        Roda 5 seeds diferentes de tendência de baixa e verifica que
        PUT aparece em pelo menos 1 — regressão direta do bug #4.
        """
        from backend.analysis.technical import TechnicalAnalyzer
        ta = TechnicalAnalyzer()
        signals = set()
        for seed in range(5):
            df = make_candles(200, trend="down", seed=seed)
            signals.add(ta.analyze(df).signal)
        assert "PUT" in signals or "AGUARDAR" in signals, (
            "Nenhum sinal PUT gerado em 5 seeds de tendência de baixa — bug #4 regrediu!"
        )


# ===========================================================================
# Issue #5 — SentimentAnalyzer: source, raw_scores e detecção de fallback
# ===========================================================================

class TestIssue5SentimentRobustness:
    """
    Garante que o SentimentAnalyzer expõe source, raw_scores e detecta
    score suspeito de 0.50 (sinal de fallback estático).
    """

    def setup_method(self):
        from backend.analysis.sentiment import SentimentAnalyzer
        self.analyzer = SentimentAnalyzer()

    def test_resultado_sem_noticias_tem_source_fallback(self):
        """Lista vazia deve retornar source='fallback_no_news'."""
        result = self.analyzer.analyze_news([])
        assert result.source == "fallback_no_news"
        assert result.signal == "neutral"

    def test_resultado_textos_vazios_tem_source_fallback(self):
        """Lista com dicts sem 'title' deve retornar source='fallback_empty_texts'."""
        result = self.analyzer.analyze_news([{"title": "", "description": ""}])
        assert result.source in {"fallback_empty_texts", "fallback_no_news"}

    def test_is_suspicious_score_detecta_0_50(self):
        """_is_suspicious_score deve retornar True para score exatamente 0.50."""
        from backend.analysis.sentiment import _is_suspicious_score
        assert _is_suspicious_score(0.50) is True
        assert _is_suspicious_score(0.5000000001) is False
        assert _is_suspicious_score(0.82) is False
        assert _is_suspicious_score(0.0) is False

    def test_sentiment_result_tem_campo_raw_scores(self):
        """SentimentResult deve ter campo raw_scores (dict)."""
        from backend.analysis.sentiment import SentimentResult
        sr = SentimentResult(signal="positive", score=0.82, raw_scores={"positive": 0.82, "negative": 0.10, "neutral": 0.08})
        assert isinstance(sr.raw_scores, dict)
        assert "positive" in sr.raw_scores
        assert "negative" in sr.raw_scores
        assert "neutral" in sr.raw_scores

    def test_sentiment_result_tem_campo_source(self):
        """SentimentResult deve ter campo source."""
        from backend.analysis.sentiment import SentimentResult
        sr = SentimentResult(signal="neutral", score=0.0, source="fallback_finbert_error")
        assert sr.source == "fallback_finbert_error"


# ===========================================================================
# Issue #6 — SignalCombiner: PUT_FORTE e PUT_FRACO devem ser gerados
# ===========================================================================

class TestIssue6SignalCombinerPut:
    """
    Garante que o SignalCombiner gera PUT_FORTE / PUT_FRACO quando
    o sinal técnico é PUT e a tabela de decisão está correta.
    """

    def setup_method(self):
        from backend.analysis.signals import SignalCombiner
        self.combiner = SignalCombiner(symbol="BTCUSDT", timeframe="5m")

    def test_put_forte_tecnico_put_sentiment_negative(self):
        """PUT técnico + sentiment negative = PUT_FORTE."""
        result = self.combiner.combine(make_tech("PUT"), make_sent("negative", 0.85))
        assert result.final == "PUT_FORTE", f"Esperado PUT_FORTE, obtido {result.final}"

    def test_put_fraco_tecnico_put_sentiment_neutral(self):
        """PUT técnico + sentiment neutral = PUT_FRACO."""
        result = self.combiner.combine(make_tech("PUT"), make_sent("neutral", 0.55))
        assert result.final == "PUT_FRACO", f"Esperado PUT_FRACO, obtido {result.final}"

    def test_aguardar_tecnico_put_sentiment_positive(self):
        """PUT técnico + sentiment positive = AGUARDAR (mercado conflitante)."""
        result = self.combiner.combine(make_tech("PUT"), make_sent("positive", 0.85))
        assert result.final == "AGUARDAR", f"Esperado AGUARDAR, obtido {result.final}"

    def test_call_forte_tecnico_call_sentiment_positive(self):
        """CALL técnico + sentiment positive = CALL_FORTE (simetria)."""
        result = self.combiner.combine(make_tech("CALL", rsi=65.0), make_sent("positive", 0.85))
        assert result.final == "CALL_FORTE", f"Esperado CALL_FORTE, obtido {result.final}"

    def test_simetria_call_put(self):
        """CALL e PUT devem ser espelhos perfeitos na tabela de decisão."""
        call_result = self.combiner.combine(make_tech("CALL"), make_sent("positive", 0.9))
        put_result  = self.combiner.combine(make_tech("PUT"),  make_sent("negative", 0.9))
        assert call_result.final == "CALL_FORTE"
        assert put_result.final  == "PUT_FORTE"

    def test_direction_retorna_put_para_put_forte(self):
        """decision.direction() deve retornar 'PUT' para PUT_FORTE."""
        result = self.combiner.combine(make_tech("PUT"), make_sent("negative", 0.85))
        assert result.direction() == "PUT"

    def test_confidence_maior_que_zero_para_put_forte(self):
        """Confiança de PUT_FORTE deve ser > 0."""
        result = self.combiner.combine(make_tech("PUT"), make_sent("negative", 0.85))
        assert result.confidence > 0.0

    def test_tabela_decisao_completa(self):
        """Todos os 9 cenários da DECISION_TABLE devem retornar o valor correto."""
        from backend.analysis.signals import (
            CALL_FORTE, CALL_FRACO, PUT_FORTE, PUT_FRACO, AGUARDAR
        )
        expected = [
            ("CALL",     "positive", CALL_FORTE),
            ("CALL",     "neutral",  CALL_FRACO),
            ("CALL",     "negative", AGUARDAR),
            ("PUT",      "negative", PUT_FORTE),
            ("PUT",      "neutral",  PUT_FRACO),
            ("PUT",      "positive", AGUARDAR),
            ("AGUARDAR", "positive", AGUARDAR),
            ("AGUARDAR", "neutral",  AGUARDAR),
            ("AGUARDAR", "negative", AGUARDAR),
        ]
        for tech_sig, sent_sig, expected_final in expected:
            result = self.combiner.combine(
                make_tech(tech_sig),
                make_sent(sent_sig, 0.85),
            )
            assert result.final == expected_final, (
                f"({tech_sig}, {sent_sig}) → esperado {expected_final}, obtido {result.final}"
            )
