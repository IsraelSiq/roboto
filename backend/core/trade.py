from dataclasses import dataclass
from typing import Optional


@dataclass
class Trade:
    """Trade simples usado pelo backtest e pelos testes.

    Os testes só dependem de:
    - direction ("LONG" ou "SHORT")
    - entry_price, exit_price
    - size
    - pnl_pct
    - result ("WIN", "LOSS" ou "PENDING")
    - is_closed, is_open(), close()
    """

    direction: str
    entry_price: float
    size: float
    stop_loss_pct: float = 1.0
    take_profit_pct: float = 2.0
    use_atr_stop: bool = False
    atr_multiplier: float = 1.5
    rr_ratio: float = 2.0

    exit_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    result: str = "PENDING"

    @property
    def is_closed(self) -> bool:
        return self.exit_price is not None

    def is_open(self) -> bool:
        return not self.is_closed

    @property
    def realized_pnl(self) -> float:
        if self.pnl_pct is None:
            return 0.0
        return self.size * (self.pnl_pct / 100.0)

    @property
    def unrealized_pnl(self) -> float:
        # Usado apenas em backtest em tempo real; para testes basta 0.0 quando fechado
        return 0.0

    def update(self, current_price: float) -> None:
        """Atualiza stop/TP e fecha posição se necessário.

        Implementação simplificada: só fecha se atingir take profit ou stop loss.
        """
        if self.is_closed:
            return

        move_pct = (current_price / self.entry_price - 1.0) * 100.0
        if self.direction == "SHORT":
            move_pct *= -1

        if move_pct >= self.take_profit_pct or move_pct <= -self.stop_loss_pct:
            self.close(current_price)

    def close(self, price: float) -> None:
        if self.is_closed:
            return
        self.exit_price = price
        move_pct = (price / self.entry_price - 1.0) * 100.0
        if self.direction == "SHORT":
            move_pct *= -1
        self.pnl_pct = move_pct
        if move_pct > 0:
            self.result = "WIN"
        elif move_pct < 0:
            self.result = "LOSS"
        else:
            self.result = "PENDING"
