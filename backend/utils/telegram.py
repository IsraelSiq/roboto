"""
Roboto — Telegram Alerts
Envia notificações para um chat do Telegram via Bot API.

Configuração (.env):
    TELEGRAM_TOKEN      — token do bot (@BotFather)
    TELEGRAM_CHAT_ID    — ID do chat
    DRAWDOWN_ALERT_PCT  — threshold de drawdown para alerta (padrão: 10.0)

Como obter o CHAT_ID:
    1. Mande qualquer mensagem pro seu bot
    2. Acesse: https://api.telegram.org/bot<TOKEN>/getUpdates
    3. Copie result[0].message.chat.id
"""

import logging
import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT = 6


class TelegramAlert:
    """
    Envia alertas para o Telegram. Falha silenciosa — nunca derruba o bot.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        self.token = token or os.getenv("TELEGRAM_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id)
        self._drawdown_alert_sent = False  # evita spam (#31)
        self._drawdown_threshold = float(os.getenv("DRAWDOWN_ALERT_PCT", "10.0"))

        if not self.enabled:
            logger.info("[Telegram] Não configurado. Alertas desativados.")

    def send(self, message: str, silent: bool = False) -> bool:
        if not self.enabled:
            return False
        try:
            url = _TELEGRAM_API.format(token=self.token)
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_notification": silent,
                "disable_web_page_preview": True,
            }
            resp = requests.post(url, json=payload, timeout=_TIMEOUT)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"[Telegram] Falha ao enviar (ignorando): {e}")
            return False

    # ----------------------------------------------------------
    # Alertas estruturados
    # ----------------------------------------------------------

    def startup(self, symbol: str, interval: str, balance: float, cycles: str = "infinito"):
        self.send(
            f"🤖 *Roboto iniciado*\n"
            f"`{symbol}` `{interval}` | Saldo: `${balance:,.2f}`\n"
            f"Ciclos: `{cycles}`"
        )

    def shutdown(self, reason: str, balance: float, cycles: int, win_rate: Optional[float] = None):
        wr = f" | Win rate: `{win_rate:.1f}%`" if win_rate is not None else ""
        self.send(
            f"🔴 *Roboto encerrado*\n"
            f"Motivo: `{reason}`\n"
            f"Saldo final: `${balance:,.2f}` | Ciclos: `{cycles}`{wr}"
        )

    def circuit_breaker(self, consecutive_losses: int, balance: float):
        """Alerta de circuit breaker (3 perdas consecutivas)."""
        self.send(
            f"⚠️ *Circuit Breaker ativado*\n"
            f"{consecutive_losses} perdas consecutivas\n"
            f"Saldo atual: `${balance:,.2f}`\n"
            f"👀 Aguardando intervenção manual."
        )

    def drawdown_alert(self, drawdown_pct: float, balance: float, symbol: str = "BTCUSDT"):
        """
        Alerta quando drawdown ultrapassa DRAWDOWN_ALERT_PCT (#31).
        Anti-spam: só envia uma vez por sessão. Reset ao chamar reset_drawdown_alert().
        """
        if self._drawdown_alert_sent:
            return
        if drawdown_pct >= self._drawdown_threshold:
            self.send(
                f"🚨 *Drawdown elevado* | `{symbol}`\n"
                f"Drawdown atual: `{drawdown_pct:.2f}%` "
                f"(limite: `{self._drawdown_threshold:.0f}%`)\n"
                f"Saldo: `${balance:,.2f}`\n"
                f"Verifique o dashboard: https://roboto-beta.vercel.app"
            )
            self._drawdown_alert_sent = True
            logger.warning(
                f"[Telegram] Drawdown alert enviado: {drawdown_pct:.2f}% ≥ {self._drawdown_threshold:.0f}%"
            )

    def reset_drawdown_alert(self):
        """Reseta o flag para permitir novo alerta (chamar quando drawdown recover)."""
        self._drawdown_alert_sent = False

    def trade_closed(self, symbol: str, direction: str, pnl_pct: float, result: str, balance: float):
        emoji = "✅" if result == "WIN" else "❌"
        self.send(
            f"{emoji} *Trade fechado* | `{symbol}` `{direction}`\n"
            f"PnL: `{pnl_pct:+.2f}%` | Saldo: `${balance:,.2f}`",
            silent=True,
        )

    def error(self, context: str, error_msg: str):
        self.send(
            f"🚨 *Erro crítico — {context}*\n"
            f"`{str(error_msg)[:200]}`"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    tg = TelegramAlert()
    if not tg.enabled:
        print("⚠️  Configure TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no .env")
    else:
        tg.startup("BTCUSDT", "5m", 10000.0)
        tg.drawdown_alert(12.5, 8750.0, "BTCUSDT")
        tg.circuit_breaker(3, 9200.0)
        tg.shutdown("Ctrl+C", 10987.0, 42, win_rate=71.4)
        print("✅ Mensagens enviadas.")
