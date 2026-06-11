"""
Roboto — Risk Manager
Controla stop loss, take profit, max trades/dia, drawdown máximo e circuit breaker.

Regras de proteção:
    - Stop loss por trade:       5% (padrão) OU ATR dinâmico
    - Take profit por trade:     10% (padrão)
    - Max trades por dia:        10 (padrão)
    - Drawdown máximo:           20% (pausa automática)
    - Circuit breaker:           3 perdas consecutivas (pausa automática)
    - Só opera sinais FORTES por padrão

Issue #7:
    - Stop loss pode usar ATR (Average True Range) quando disponível.
    - Fórmula:
        CALL -> stop_loss = entry_price - (atr * atr_multiplier)
        PUT  -> stop_loss = entry_price + (atr * atr_multiplier)
    - Se ATR não estiver disponível, cai para o SL percentual atual.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import Optional
from uuid import uuid4

from backend.analysis.signals import SignalDecision, AGUARDAR

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Representa um trade aberto ou fechado."""
    id: str
    symbol: str
    direction: str              # CALL | PUT
    strength: str               # FORTE | FRACO
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: str
    signal_decision: Optional[SignalDecision] = None
    exit_price: Optional[float] = None
    closed_at: Optional[str] = None
    result: str = "PENDING"     # WIN | LOSS | PENDING
    pnl_pct: Optional[float] = None
    stop_loss_mode: str = "pct" # 'pct' | 'atr'
    atr_at_entry: Optional[float] = None

    def is_open(self) -> bool:
        return self.result == "PENDING"

    def pnl_summary(self) -> str:
        if self.pnl_pct is None:
            return "PENDING"
        emoji = "✅" if self.pnl_pct > 0 else "❌"
        return f"{emoji} {self.result} | PnL: {self.pnl_pct:+.2f}%"


class RiskManager:
    """
    Gerencia risco por trade e por dia.

    Args:
        balance:                 Saldo inicial em USDT
        stop_loss_pct:           Stop loss em % (padrão: 5.0)
        take_profit_pct:         Take profit em % (padrão: 10.0)
        max_trades_day:          Máx trades por dia (padrão: 10)
        max_drawdown_pct:        Drawdown máximo antes de pausar (padrão: 20.0)
        only_strong:             Só opera sinais FORTES (padrão: True)
        use_atr_stop:            Quando True, usa ATR para o stop loss se disponível
        atr_multiplier:          Multiplicador do ATR para calcular distância do stop
        max_consecutive_losses:  Circuit breaker: pausa após N perdas seguidas (padrão: 3)
    """

    def __init__(
        self,
        balance: float = 10000.0,
        stop_loss_pct: float = 5.0,
        take_profit_pct: float = 10.0,
        max_trades_day: int = 10,
        max_drawdown_pct: float = 20.0,
        only_strong: bool = True,
        use_atr_stop: bool = False,
        atr_multiplier: float = 2.0,
        max_consecutive_losses: int = 3,
    ):
        self.initial_balance = balance
        self.balance = balance
        self.peak_balance = balance
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_trades_day = max_trades_day
        self.max_drawdown_pct = max_drawdown_pct
        self.only_strong = only_strong
        self.use_atr_stop = use_atr_stop
        self.atr_multiplier = atr_multiplier
        self.max_consecutive_losses = max_consecutive_losses

        self._paused = False
        self._pause_reason = ""
        self._trades: list[Trade] = []
        self._open_trade: Optional[Trade] = None
        self._today_count = 0
        self._today_date: Optional[date] = None
        self._consecutive_losses = 0

    def can_trade(
        self,
        decision: SignalDecision,
        current_date: Optional[date] = None,
    ) -> tuple[bool, str]:
        if self._paused:
            return False, f"Bot pausado: {self._pause_reason}"

        if decision.final == AGUARDAR:
            return False, "Sinal AGUARDAR — sem operação"

        if self.only_strong and not decision.is_strong():
            return False, f"Sinal fraco ({decision.final}) — only_strong=True"

        if self._open_trade is not None:
            return False, f"Trade aberto em {self._open_trade.symbol} desde {self._open_trade.opened_at}"

        self._reset_daily_count_if_needed(current_date)
        if self._today_count >= self.max_trades_day:
            return False, f"Limite diário atingido ({self._today_count}/{self.max_trades_day})"

        drawdown = self._calc_drawdown()
        if drawdown >= self.max_drawdown_pct:
            self._pause(f"Drawdown {drawdown:.1f}% >= {self.max_drawdown_pct}%")
            return False, self._pause_reason

        return True, ""

    def open_trade(
        self,
        decision: SignalDecision,
        current_date: Optional[date] = None,
    ) -> Trade:
        self._reset_daily_count_if_needed(current_date)

        price = decision.current_price
        direction = decision.direction()
        atr_value = getattr(decision, "atr", None)

        sl, sl_mode = self._calc_stop_loss(price=price, direction=direction, atr_value=atr_value)
        tp = self._calc_take_profit(price=price, direction=direction)

        trade = Trade(
            id=str(uuid4())[:8],
            symbol=decision.symbol,
            direction=direction,
            strength=decision.strength(),
            entry_price=price,
            stop_loss=sl,
            take_profit=tp,
            opened_at=datetime.now(timezone.utc).isoformat(),
            signal_decision=decision,
            stop_loss_mode=sl_mode,
            atr_at_entry=atr_value if sl_mode == "atr" else None,
        )

        self._open_trade = trade
        self._trades.append(trade)
        self._today_count += 1

        atr_note = f" | ATR={atr_value} x {self.atr_multiplier}" if sl_mode == "atr" else ""
        logger.info(
            f"[Trade ABERTO] {direction} {decision.symbol} @ ${price:,.2f} "
            f"| SL=${sl:,.2f} ({sl_mode}) | TP=${tp:,.2f} | ID={trade.id}{atr_note}"
        )
        return trade

    def close_trade(self, trade: Trade, exit_price: float) -> Trade:
        if trade.direction == "CALL":
            pnl_pct = (exit_price - trade.entry_price) / trade.entry_price * 100
        else:
            pnl_pct = (trade.entry_price - exit_price) / trade.entry_price * 100

        trade.exit_price = exit_price
        trade.closed_at = datetime.now(timezone.utc).isoformat()
        trade.pnl_pct = round(pnl_pct, 4)
        trade.result = "WIN" if pnl_pct > 0 else "LOSS"

        if trade not in self._trades:
            self._trades.append(trade)

        self.balance = round(self.balance * (1 + pnl_pct / 100), 2)

        if self.balance > self.peak_balance:
            self.peak_balance = self.balance

        self._open_trade = None

        # Circuit breaker
        if trade.result == "WIN":
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self.max_consecutive_losses:
                self._pause(
                    f"Circuit breaker: {self._consecutive_losses} perdas consecutivas "
                    f">= {self.max_consecutive_losses}"
                )

        logger.info(f"[Trade FECHADO] ID={trade.id} | {trade.pnl_summary()} | Saldo: ${self.balance:,.2f}")

        drawdown = self._calc_drawdown()
        if drawdown >= self.max_drawdown_pct and not self._paused:
            self._pause(f"Drawdown {drawdown:.1f}% >= {self.max_drawdown_pct}%")

        return trade

    def check_exit(self, trade: Trade, current_price: float) -> Optional[str]:
        if trade.direction == "CALL":
            if current_price <= trade.stop_loss:
                return "SL"
            if current_price >= trade.take_profit:
                return "TP"
        else:
            if current_price >= trade.stop_loss:
                return "SL"
            if current_price <= trade.take_profit:
                return "TP"
        return None

    def pause(self, reason: str = "Manual"):
        self._pause(reason)

    def resume(self):
        self._paused = False
        self._pause_reason = ""
        self._consecutive_losses = 0
        logger.info("RiskManager retomado.")

    def is_paused(self) -> bool:
        return self._paused

    def status(self) -> dict:
        self._reset_daily_count_if_needed()
        return {
            "balance": self.balance,
            "initial_balance": self.initial_balance,
            "drawdown_pct": round(self._calc_drawdown(), 2),
            "trades_today": self._today_count,
            "max_trades_day": self.max_trades_day,
            "open_trade": self._open_trade.id if self._open_trade else None,
            "paused": self._paused,
            "pause_reason": self._pause_reason,
            "total_trades": len(self._trades),
            "consecutive_losses": self._consecutive_losses,
            "max_consecutive_losses": self.max_consecutive_losses,
        }

    def _pause(self, reason: str):
        self._paused = True
        self._pause_reason = reason
        logger.warning(f"[RiskManager] BOT PAUSADO: {reason}")

    def _calc_drawdown(self) -> float:
        if self.peak_balance == 0:
            return 0.0
        return max((self.peak_balance - self.balance) / self.peak_balance * 100, 0.0)

    def _reset_daily_count_if_needed(self, current_date: Optional[date] = None):
        today = current_date or date.today()
        if self._today_date != today:
            self._today_date = today
            self._today_count = 0

    def _calc_stop_loss(self, price: float, direction: str, atr_value: Optional[float]) -> tuple[float, str]:
        if self.use_atr_stop and atr_value is not None and atr_value > 0:
            distance = atr_value * self.atr_multiplier
            if direction == "CALL":
                return round(price - distance, 2), "atr"
            return round(price + distance, 2), "atr"

        if direction == "CALL":
            return round(price * (1 - self.stop_loss_pct / 100), 2), "pct"
        return round(price * (1 + self.stop_loss_pct / 100), 2), "pct"

    def _calc_take_profit(self, price: float, direction: str) -> float:
        if direction == "CALL":
            return round(price * (1 + self.take_profit_pct / 100), 2)
        return round(price * (1 - self.take_profit_pct / 100), 2)

    @property
    def trades(self) -> list[Trade]:
        return list(self._trades)

    @property
    def closed_trades(self) -> list[Trade]:
        return [t for t in self._trades if not t.is_open()]
