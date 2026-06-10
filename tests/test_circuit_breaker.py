"""
Testes — Circuit Breaker (issue #20)
Cobre o comportamento de pausa após N perdas consecutivas no RiskManager.
"""
import pytest
from backend.risk.manager import RiskManager
from backend.analysis.signals import SignalDecision


def make_decision(signal="CALL_FORTE", price=60000.0):
    return SignalDecision(
        final=signal,
        technical_signal="CALL",
        sentiment_signal="positive",
        reason="teste",
        confidence=0.9,
        symbol="BTCUSDT",
        timeframe="5m",
        current_price=price,
        rsi=40.0,
        sentiment_score=0.8,
        news_count=3,
    )


class TestCircuitBreaker:
    def _make_rm(self, max_losses=3):
        return RiskManager(balance=10000.0, only_strong=False, max_consecutive_losses=max_losses)

    def _lose(self, rm, n=1):
        """Executa N trades com loss consecutivos."""
        for _ in range(n):
            if rm.is_paused():
                break
            ok, _ = rm.can_trade(make_decision())
            if not ok:
                break
            trade = rm.open_trade(make_decision())
            rm.close_trade(trade, trade.stop_loss)  # sempre perde no SL

    # -----------------------------------------------------------------

    def test_not_paused_before_limit(self):
        """N-1 perdas não devem acionar o circuit breaker."""
        rm = self._make_rm(max_losses=3)
        self._lose(rm, n=2)
        assert not rm.is_paused()

    def test_paused_after_n_losses(self):
        """Exatamente N perdas devem pausar o bot."""
        rm = self._make_rm(max_losses=3)
        self._lose(rm, n=3)
        assert rm.is_paused()

    def test_pause_reason_mentions_circuit_breaker(self):
        rm = self._make_rm(max_losses=3)
        self._lose(rm, n=3)
        assert "Circuit breaker" in rm._pause_reason or "circuit" in rm._pause_reason.lower()

    def test_blocked_after_pause(self):
        """Após pausa, can_trade deve retornar False."""
        rm = self._make_rm(max_losses=2)
        self._lose(rm, n=2)
        ok, reason = rm.can_trade(make_decision())
        assert ok is False

    def test_consecutive_counter_resets_on_win(self):
        """Uma vitória deve zerar o contador de perdas consecutivas."""
        rm = self._make_rm(max_losses=3)
        self._lose(rm, n=2)
        # agora uma vitória
        ok, _ = rm.can_trade(make_decision())
        assert ok is True
        trade = rm.open_trade(make_decision())
        rm.close_trade(trade, trade.take_profit)  # WIN
        assert rm._consecutive_losses == 0

    def test_custom_max_losses(self):
        """Deve respeitar o parâmetro max_consecutive_losses customizado."""
        rm = self._make_rm(max_losses=5)
        self._lose(rm, n=4)
        assert not rm.is_paused()
        self._lose(rm, n=1)
        assert rm.is_paused()

    def test_max_losses_one(self):
        """max_losses=1 deve pausar na primeira perda."""
        rm = self._make_rm(max_losses=1)
        self._lose(rm, n=1)
        assert rm.is_paused()
