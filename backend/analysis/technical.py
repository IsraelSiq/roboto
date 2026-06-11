"""
Roboto — Análise Técnica
Calcula RSI, EMA50, MACD, Bollinger Bands e ATR usando pandas-ta-classic.
Gera sinal técnico: CALL | PUT | AGUARDAR

Estratégia (scoring 4 indicadores, min_score=2):
    CALL: RSI > rsi_call_threshold | MACD bullish | Preço>EMA50 | BB lower
    PUT:  RSI < rsi_put_threshold  | MACD bearish | Preço<EMA50 | BB upper
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
        rsi_overbought:    Nível de sobrecompra para RSI PUT (padrão: 70)
        rsi_oversold:      Nível de sobrevenda para RSI CALL (padrão: 30)
        rsi_call_threshold: RSI acima deste valor pontua CALL (padrão: 55)
        rsi_put_threshold:  RSI abaixo deste valor pontua PUT (padrão: 45)
        min_score:         Pontuação mínima para gerar sinal (padrão: 2)
        min_candles:       Mínimo de candles (padrão: 60)
        atr_period:        Período do ATR (padrão: 14)
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
        rsi_call_threshold: int = 55,
        rsi_put_threshold: int = 45,
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
        self.rsi_call_threshold = rsi_call_threshold
        self.rsi_put_threshold = rsi_put_threshold
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
                    elif macd_prev >= sig_prev and macd_val < macd_sig:
                        macd_cross = "DOWN"

            bb_upper, bb_lower = None, None
            bb_df = ta.bbands(df["close"], length=self.bb_period, std=self.bb_std)
            if bb_df is not None and not bb_df.empty:
                uc = [c for c in bb_df.columns if "BBU" in c]
                lc = [c for c in bb_df.columns if "BBL" in c]
                if uc and lc:
                    bb_upper = float(bb_df[uc[0]].iloc[-1])
                    bb_lower = float(bb_df[lc[0]].iloc[-1])

            atr = None
            atr_s = ta.atr(df["high"], df["low"], df["close"], length=self.atr_period)
            if atr_s is not None and not atr_s.empty:
                atr = float(atr_s.iloc[-1])

            price = float(df["close"].iloc[-1])
            price_vs_ema = self._price_vs_ema(price, ema50)
            price_vs_bb  = self._price_vs_bb(price, bb_upper, bb_lower)

            signal, reason = self._generate_signal(
                rsi=rsi, macd_val=macd_val, macd_sig=macd_sig,
                macd_cross=macd_cross, price_vs_ema=price_vs_ema, price_vs_bb=price_vs_bb,
            )

            return TechnicalResult(
                signal=signal, reason=reason,
                rsi=round(rsi, 2) if rsi is not None else None,
                macd=round(macd_val, 4) if macd_val is not None else None,
                macd_signal=round(macd_sig, 4) if macd_sig is not None else None,
                macd_cross=macd_cross,
                ema50=round(ema50, 2) if ema50 is not None else None,
                bb_upper=round(bb_upper, 2) if bb_upper is not None else None,
                bb_lower=round(bb_lower, 2) if bb_lower is not None else None,
                atr=round(atr, 4) if atr is not None else None,
                current_price=round(price, 2),
                price_vs_ema=price_vs_ema,
                price_vs_bb=price_vs_bb,
            )
        except Exception as e:
            logger.error(f"Erro na análise técnica: {e}")
            return TechnicalResult(signal="AGUARDAR", reason=f"Erro interno: {e}")

    def _generate_signal(self, rsi, macd_val, macd_sig, macd_cross, price_vs_ema, price_vs_bb):
        call_score, call_reasons = 0, []
        put_score,  put_reasons  = 0, []

        if rsi is not None:
            if rsi > self.rsi_call_threshold:
                call_score += 1
                call_reasons.append(f"RSI={rsi:.1f}>{self.rsi_call_threshold}")
            elif rsi < self.rsi_put_threshold:
                put_score += 1
                put_reasons.append(f"RSI={rsi:.1f}<{self.rsi_put_threshold}")

        if macd_val is not None and macd_sig is not None:
            if macd_cross == "UP" or macd_val > macd_sig:
                call_score += 1
                call_reasons.append("MACD bullish")
            if macd_cross == "DOWN" or macd_val < macd_sig:
                put_score += 1
                put_reasons.append("MACD bearish")

        if price_vs_ema == "ABOVE":
            call_score += 1
            call_reasons.append("Preço>EMA50")
        elif price_vs_ema == "BELOW":
            put_score += 1
            put_reasons.append("Preço<EMA50")

        if price_vs_bb == "LOWER":
            call_score += 1
            call_reasons.append("BB lower")
        elif price_vs_bb == "UPPER":
            put_score += 1
            put_reasons.append("BB upper")

        if call_score >= self.min_score and call_score > put_score:
            return "CALL", " | ".join(call_reasons)
        if put_score >= self.min_score and put_score > call_score:
            return "PUT", " | ".join(put_reasons)
        if call_score >= self.min_score and call_score == put_score:
            return "AGUARDAR", f"Empate CALL={call_score} PUT={put_score}"

        return "AGUARDAR", f"Score insuficiente (CALL={call_score} PUT={put_score} min={self.min_score})"

    @staticmethod
    def _price_vs_ema(price: float, ema: Optional[float]) -> str:
        if ema is None: return "UNKNOWN"
        diff = (price - ema) / ema
        if diff > 0.001: return "ABOVE"
        if diff < -0.001: return "BELOW"
        return "AT"

    @staticmethod
    def _price_vs_bb(price: float, bb_upper: Optional[float], bb_lower: Optional[float]) -> str:
        if bb_upper is None or bb_lower is None: return "UNKNOWN"
        if price >= bb_upper: return "UPPER"
        if price <= bb_lower: return "LOWER"
        return "MIDDLE"
