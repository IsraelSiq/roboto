"""
Testes — TelegramAlert (issue #22)
Garante comportamento offline seguro e formatação das mensagens.
"""
import pytest
from unittest.mock import patch, MagicMock
from backend.utils.telegram import TelegramAlert


class TestTelegramAlertOffline:
    """Sem token/chat_id — tudo deve ser silencioso."""

    def setup_method(self):
        # Garante que não há token/chat_id mesmo que o .env local tenha credenciais
        self.tg = TelegramAlert(token="", chat_id="")

    def test_disabled_without_credentials(self):
        # Instancia diretamente sem ler o .env
        tg = TelegramAlert.__new__(TelegramAlert)
        tg.token = ""
        tg.chat_id = ""
        tg.enabled = bool(tg.token and tg.chat_id)
        assert tg.enabled is False

    def test_send_returns_false_when_disabled(self):
        assert self.tg.send("qualquer mensagem") is False

    def test_startup_does_not_raise(self):
        self.tg.startup(symbol="BTCUSDT", interval="5m", balance=10000.0)

    def test_shutdown_does_not_raise(self):
        self.tg.shutdown(reason="teste", balance=10000.0, cycles=5)

    def test_circuit_breaker_does_not_raise(self):
        self.tg.circuit_breaker(consecutive_losses=3, balance=9000.0)

    def test_trade_closed_does_not_raise(self):
        self.tg.trade_closed(
            symbol="BTCUSDT", direction="CALL",
            pnl_pct=2.5, result="WIN", balance=10200.0
        )

    def test_error_does_not_raise(self):
        self.tg.error("loop principal", "NullPointerException")


class TestTelegramAlertOnline:
    """Com credenciais fake — valida mensagens enviadas via requests.post mock."""

    def setup_method(self):
        self.tg = TelegramAlert(token="fake_token", chat_id="12345")

    def test_enabled_with_credentials(self):
        assert self.tg.enabled is True

    def _mock_post(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return patch("requests.post", return_value=resp)

    def test_send_calls_requests_post(self):
        with self._mock_post() as mock_post:
            result = self.tg.send("olá mundo")
        assert result is True
        mock_post.assert_called_once()

    def test_send_silent_flag(self):
        with self._mock_post() as mock_post:
            self.tg.send("msg silenciosa", silent=True)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["disable_notification"] is True

    def test_startup_message_contains_symbol(self):
        with self._mock_post() as mock_post:
            self.tg.startup(symbol="ETHUSDT", interval="1m", balance=5000.0)
        payload = mock_post.call_args.kwargs["json"]
        assert "ETHUSDT" in payload["text"]

    def test_trade_closed_win_contains_check(self):
        with self._mock_post() as mock_post:
            self.tg.trade_closed("BTCUSDT", "CALL", 9.5, "WIN", 10900.0)
        payload = mock_post.call_args.kwargs["json"]
        assert "✅" in payload["text"]

    def test_trade_closed_loss_contains_x(self):
        with self._mock_post() as mock_post:
            self.tg.trade_closed("BTCUSDT", "PUT", -5.0, "LOSS", 9500.0)
        payload = mock_post.call_args.kwargs["json"]
        assert "❌" in payload["text"]

    def test_trade_closed_is_silent(self):
        """Trade fechado deve ter notificação silenciosa."""
        with self._mock_post() as mock_post:
            self.tg.trade_closed("BTCUSDT", "CALL", 3.0, "WIN", 10300.0)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["disable_notification"] is True

    def test_circuit_breaker_message(self):
        with self._mock_post() as mock_post:
            self.tg.circuit_breaker(consecutive_losses=3, balance=8500.0)
        payload = mock_post.call_args.kwargs["json"]
        assert "⚠️" in payload["text"] or "Circuit" in payload["text"]

    def test_shutdown_includes_win_rate(self):
        with self._mock_post() as mock_post:
            self.tg.shutdown(reason="Ctrl+C", balance=11000.0, cycles=20, win_rate=65.0)
        payload = mock_post.call_args.kwargs["json"]
        assert "65.0" in payload["text"]

    def test_send_returns_false_on_request_exception(self):
        with patch("requests.post", side_effect=Exception("timeout")):
            result = self.tg.send("qualquer")
        assert result is False
