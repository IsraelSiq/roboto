"""
Roboto — Análise Técnica
Calcula RSI, EMA50, MACD, Bollinger Bands e ATR usando pandas-ta-classic.
Gera sinal técnico: CALL | PUT | AGUARDAR

Estratégia (scoring 4 indicadores, min_score=2):
    CALL: RSI<overbought | MACD bullish | Preço>EMA50 | BB lower
    PUT:  RSI>oversold   | MACD bearish | Preço<EMA50 | BB upper
    score >= min_score e maior que o oposto → CALL ou PUT

Issue #7:
    - Expõe ATR(14) no TechnicalResult para permitir stop loss dinâmico.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import pandas_ta_classic as ta

logger = logging.getLogger(__name__)


@dataclass
class TechnicalResult:
    signal: str
    reason: str
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_cross: Optional[str] = None
    ema50: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    atr: Optional[float] = None
    current_price: Optional[float] = None
    price_vs_ema: Optional[str] = None
    price_vs_bb: Optional[str] = None


class TechnicalAnalyzer:
    """
    Scoring de 4 indicadores. Sinal gerado quando score >= min_score
    e maior que o score oposto.

    Args:
        rsi_overbought: Nível de sobrecompra (padrão: 70)
        rsi_oversold:   Nível de sobrevenda (padrão: 30)
        min_score:      Pontuação mínima para gerar sinal (padrão: 2)
        min_candles:    Mínimo de candles (padrão: 60)
        atr_period:     Período do ATR (padrão: 14)
    """

    def __init__(
        self,
        rsi_period: int = 14,
        ema_period: int = 50,
        bb_period: int = 20,
        bb_std: float = 2.0,
        atr_period: int = 14,
        rsi_overbought: int = 70,
        rsi_oversold: int = 30,
        min_score: int = 2,
        min_candles: int = 60,
    ):
        self.rsi_period = rsi_period
        self.ema_period = ema_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.min_score = min_score
        self.min_candles = min_candles

    def analyze(self, df: pd.DataFrame) -> TechnicalResult:
        if df.empty or len(df) < self.min_candles:
            return TechnicalResult(
                signal="AGUARDAR",
                reason=f"Candles insuficientes ({len(df)}/{self.min_candles})"
            )
        df = df.copy()
        try:
            rsi_s = ta.rsi(df["close"], length=self.rsi_period)
            rsi = float(rsi_s.iloc[-1]) if rsi_s is not None else None

            ema_s = ta.ema(df["close"], length=self.ema_period)
            ema50 = float(ema_s.iloc[-1]) if ema_s is not None else None

            macd_val, macd_sig, macd_cross = None, None, "NONE"
            macd_df = ta.macd(df["close"])
            if macd_df is not None and not macd_df.empty:
                cols = macd_df.columns.tolist()
                mc = [c for c in cols if c.startswith("MACD_") and "s" not in c.lower() and "h" not in c.lower()]
                sc = [c for c in cols if "MACDs" in c]
                if mc and sc:
                    macd_val  = float(macd_df[mc[0]].iloc[-1])
                    macd_sig  = float(macd_df[sc[0]].iloc[-1])
                    macd_prev = float(macd_df[mc[0]].iloc[-2])
                    sig_prev  = float(macd_df[sc[0]].iloc[-2])
                    if macd_prev <= sig_prev and macd_val > macd_sig:
                        macd_cross = "UP"
                    elif macd_prev >= sig_p