"""
Testes — SignalCombiner
"""
import pytest
from unittest.mock import MagicMock
from backend.analysis.signals import SignalCombiner


def make_tech(signal="CALL", rsi=30.0, price=60000.0):
    t = MagicMock()
    t.signal = signal
    t.rsi = rsi
    t.current_price = price
    t.macd_cross = "bullish"
    t.price_vs_ema = "above"
    return t


def make_sent(signal="positive", score=0.85, count=5):
    s = MagicMock()
    s.signal = signal
    s.score = score
    s.news_count = count
    s.reason = "test"
    return s


class TestSignalCombiner:
    def setup_method(self):
        self.combiner = SignalCombiner(symbol="BTCUSDT", timeframe="5m")

    def test_call_forte_when_aligned(self):
        """Técnico CALL + sentiment positive = CALL_FORTE."""
        result = self.combiner.combine(make_tech("CALL", rsi=28), make_sent("positive", 0.9))
        assert result.final in {"CALL_FORTE", "CALL_FRACO"}

    def test_put_forte_when_aligned(self):
        """Técnico PUT + sentiment negative = PUT_FORTE."""
        result = self.combiner.combine(make_tech("PUT", rsi=72), make_sent("negative", 0.9))
        assert result.final in {"PUT_FORTE", "PUT_FRACO"}

    def test_aguardar_when_conflicting(self):
        """Técnico CALL + sentiment negative forte = AGUARDAR."""
        result = self.combiner.combine(make_tech("CALL", rsi=50), make_sent("negative", 0.95))
        assert result.final in {"AGUARDAR", "CALL_FRACO"}

    def test_result_has_required_fields(self):
        result = self.combiner.combine(make_tech(), make_sent())
        assert hasattr(result, "final")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reason")

    def test_confidence_between_0_and_1(self):
        result = self.combiner.combine(make_tech(), make_sent())
        assert 0.0 <= result.confidence <= 1.0

    def test_summary_returns_string(self):
        result = self.combiner.combine(make_tech(), make_sent())
        assert isinstance(result.summary(), str)
