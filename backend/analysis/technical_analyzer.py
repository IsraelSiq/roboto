import logging
from dataclasses import dataclass

import pandas as pd

from backend.analysis.technical import TechnicalAnalysis, TechnicalResult

logger = logging.getLogger(__name__)


@dataclass
class TechnicalAnalyzer:
    min_candles: int = 60
    atr_period: int = 14
    # thresholds usados pelos testes de issues #4/#6
    rsi_call_threshold: float = 55.0
    rsi_put_threshold: float = 45.0

    def analyze(self, df: pd.DataFrame) -> TechnicalResult:
        if len(df) < self.min_candles:
            return TechnicalResult(
                signal="AGUARDAR",
                reason="Candles insuficientes para análise técnica",
                rsi=None,
                current_price=None,
                ema50=None,
                macd=None,
                macd_signal=None,
                bb_upper=None,
                bb_lower=None,
                atr=None,
                price_vs_ema=None,
            )

        df = df.copy()
        df = TechnicalAnalysis.add_indicators(df)

        df["atr"] = TechnicalAnalysis.atr(df, self.atr_period)

        close = df["close"].iloc[-1]
        ema50 = df["ema_50"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]
        macd = df["macd_line"].iloc[-1]
        macd_signal = df["macd_signal"].iloc[-1]
        bb_upper = df["bb_upper"].iloc[-1]
        bb_lower = df["bb_lower"].iloc[-1]
        atr = df["atr"].iloc[-1]

        if close > ema50 * 1.01:
            price_vs_ema = "ABOVE"
        elif close < ema50 * 0.99:
            price_vs_ema = "BELOW"
        else:
            price_vs_ema = "AT"

        # lógica simples para emitir CALL/PUT/AGUARDAR baseada em RSI
        if rsi > self.rsi_call_threshold:
            signal = "CALL"
        elif rsi < self.rsi_put_threshold:
            signal = "PUT"
        else:
            signal = "AGUARDAR"

        return TechnicalResult(
            signal=signal,
            reason="Análise técnica calculada",
            rsi=float(rsi),
            current_price=float(close),
            ema50=float(ema50),
            macd=float(macd),
            macd_signal=float(macd_signal),
            bb_upper=float(bb_upper),
            bb_lower=float(bb_lower),
            atr=float(atr),
            price_vs_ema=price_vs_ema,
        )
