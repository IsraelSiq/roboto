"""
Roboto — Telegram Alerts
Envia notificações para um chat do Telegram via Bot API.
Nenhuma biblioteca externa — usa apenas `requests` (já no requirements.txt).

Configuração (.env):
    TELEGRAM_TOKEN   — token do bot (obtenha com @BotFather)
    TELEGRAM_CHAT_ID — ID do chat/grupo que receberá as mensagens

Como obter o CHAT_ID:
    1. Mande qualquer mensagem pro seu bot
    2. Acesse: https://api.telegram.org/bot<TOKEN>/getUpdates
    3. Copie o valor de result[0].message.chat.id

Uso:
    from backend.utils.telegram import TelegramAlert
    tg = TelegramAlert()
    tg.send("🟢 Roboto iniciado | BTCUSDT 5m")
"""

import logging
import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT = 6  # segundos — falha silenciosa para não travar o bot


class TelegramAlert:
    """
    Envia alertas para o Telegram. Falha silenciosa: nunca derruba o bot.

    Args:
        token:   Token do bot (padrão: env TELEGRAM_TOKEN)
        chat_id: ID do chat (padrão: env TELEGRAM_CHAT_ID)
    """

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        self.token = token or os.getenv("TELEGRAM_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id)

        if not self.enabled:
            logger.info(
                "[Telegram] TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não configurados. "
                "Alertas desativados."
            )

    def send(self, message: str, silent: bool = False) -> bool:
        """
        Envia uma mensagem de texto para o Telegram.

        Args:
            message: Texto da mensagem (suporta Markdown)
            silent:  Se True, notificação sem som no celular

        Returns:
            True se enviado com sucesso, False caso contrário
        """
        if not self.enabled:
            return False

        try:
            url = _TELEGRAM_API.format(token=self.token)
            payload = {
                "chat_id":                  self.chat_id,
                "text":                     message,
                "parse_mode":               "Markdown",
                "disable_notification":     silent,
                "disable_web_page_preview": True,
            }
            resp = requests.post(url, json=payload, timeout=_TIMEOUT)
            resp.raise_for_status()
            logger.debug(f"[Telegram] Mensagem enviada: {message[:60]!r}")
            return True
        except Exception as e:
            logger.warning(f"[Telegram] Falha ao enviar mensagem (ignorando): {e}")
            return False

    def startup(self, symbol: str, interval: str, balance: float, cycles: str = "infinito"):
        """Notifica inicialização do bot."""
        msg = (
            f"🤖 *Roboto iniciado*\n"
            f"`{symbol}` `{interval}` | Saldo: `${balance:,.2f}`\n"
            f"Ciclos: `{cycles}`"
        )
        self.send(msg)

    def shutdown(self, reason: str, balance: float, cycles: int, win_rate: Optional[float] = None):
        """Notifica encerramento do bot."""
        wr = f" | Win rate: `{win_rate:.1f}%`" if win_rate is not None else ""
        msg = (
            f"🔴 *Roboto encerrado*\n"
            f"Motivo: `{reason}`\n"
            f"Saldo final: `${balance:,.2f}` | Ciclos: `{cycles}`{wr}"
        )
        self.send(msg)

    def circuit_breaker(self, consecutive_losses: int, balance: float):
        """Notifica ativação do circuit breaker."""
        msg = (
            f"⚠️ *Circuit Breaker ativado*\n"
            f"{consecutive_losses} perdas consecutivas\n"
            f"Saldo atual: `${balance:,.2f}`\n"
            f"👀 Aguardando intervenção manual."
        )
        self.send(msg)

    def trade_closed(self, symbol: str, direction: str, pnl_pct: float, result: str, balance: float):
        """Notifica fechamento de trade (silencioso — sem som)."""
        emoji = "✅" if result == "WIN" else "❌"
        msg = (
            f"{emoji} *Trade fechado* | `{symbol}` `{direction}`\n"
            f"PnL: `{pnl_pct:+.2f}%` | Saldo: `${balance:,.2f}`"
        )
        self.send(msg, silent=True)

    def error(self, context: str, error_msg: str):
        """Notifica erro crítico."""
        msg = (
            f"🚨 *Erro crítico — {context}*\n"
            f"`{str(error_msg)[:200]}`"
        )
        self.send(msg)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)

    tg = TelegramAlert()
    if not tg.enabled:
        print("⚠️  TELEGRAM_TOKEN e TELEGRAM_CHAT_ID não configurados no .env")
        print("   Configure e rode novamente para testar.")
    else:
        print("Enviando mensagens de teste...")
        tg.startup(symbol="BTCUSDT", interval="5m", balance=10000.0)
        tg.trade_closed("BTCUSDT", "CALL", +9.87, "WIN", 10987.0)
        tg.circuit_breaker(consecutive_losses=3, balance=9200.0)
        tg.shutdown(reason="Ctrl+C", balance=10987.0, cycles=42, win_rate=71.4)
        print("✅ Mensagens enviadas. Verifique o Telegram.")
