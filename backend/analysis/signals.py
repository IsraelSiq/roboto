import logging
from dataclasses import dataclass
from typing import List

from backend.analysis.technical import TechnicalAnalysis

logger = logging.getLogger(__name__)


SYMBOL_KEYWORDS = {
    "BTCUSDT": ["bitcoin", "btc"],
    "ETHUSDT": ["ethereum", "eth"],
}


@dataclass
class Signal:
    symbol: str
    direction: int
    strength: str
    reason: str


class SignalGenerator:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol

    def generate(self, df) -> List[Signal]:
        df = TechnicalAnalysis.add_indicators(df.copy())
        df = TechnicalAnalysis.generate_signal(df)

        signals: List[Signal] = []
        for idx, row in df.iterrows():
            if row.get("signal", 0) == 0:
                continue
            direction = int(row["signal"])
            strength = row.get("strength", "weak")
            reason = "technical"
            signals.append(
                Signal(
                    symbol=self.symbol,
                    direction=direction,
                    strength=strength,
                    reason=reason,
                )
            )
        return signals
