from pydantic import BaseModel
from typing import Optional


class BacktestRequest(BaseModel):
    """Schema de entrada para o endpoint /backtest.

    Foi desenhado para casar com o uso em backend.api.routes e com os
    testes de integração de backtest.
    """

    symbol: str
    interval: str
    start: str
    end: str
    balance: float = 10000.0
    weak: bool = False
    sentiment: str = "positive"  # "positive", "negative", "both", "neutral"
    atr: bool = False
    atr_mult: float = 2.0
    rr: float = 2.0
    macro: bool = False
    macro_tf: Optional[str] = None
    no_save: bool = False
