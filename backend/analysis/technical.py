"""
Roboto — Análise Técnica
Calcula RSI, EMA50, MACD e Bollinger Bands usando pandas-ta-classic.
Gera sinal técnico: CALL | PUT | AGUARDAR

Estratégia (scoring 4 indicadores):
    Pontuação máxima: 4 pontos por direção

    CALL:
        +1  RSI < rsi_overbought (não sobrecomprado)
        +1  MACD cruzou pra cima OU MACD > Signal
        +1  Preço acima da EMA50
        +1  Preço tocou ou está abaixo da BB lower (pullback)

    PUT:
        +1  RSI > rsi_oversold (não sobrevendido)
        +1  MACD cruzou pra baixo OU MACD < Signal
        +1  Preço abaixo da EMA50
        +1  Preço tocou ou está acima da BB upper (sobrecomprado)

    score >= 3  → CALL ou PUT
    score <= 1  → AGUARDAR
    score == 2  → AGUARDAR (zona de indecisão)

Uso:
    from backend.analysis.technical import TechnicalAnalyzer
    ta = TechnicalAnalyzer()
    result = ta.analyze(df_candles)
    print(result.signal)   # CALL | PUT | AGUARDAR
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import pandas_ta_classic as ta

logger = logging.getLogger(__name__)


@dataclass
class TechnicalResult:
    """Resultado completo da análise técnica."""
    signal: str              # CALL | PUT | AGUARDAR
    reason: str
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_cross: Optional[str] = None   # UP | DOWN | NONE
    ema50: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    current_price: Optional[float] = None
    price_vs_ema: Optional[str] = None  # ABOVE | BELOW | AT
    price_vs_bb: Optional[str] = None   # UPPER | LOWER | MIDDLE


class TechnicalAnalyzer:
    """
    Analisador técnico com scoring de 4 indicadores.
    Sinal gerado quando score >= min_score (padrão: 3/4).

    Args:
        rsi_period:      Período do RSI (padrão: 14)
        ema_period:      Período da EMA (padrão: 50)
        bb_period:       Período das Bollinger Bands (padrão: 20)
        bb_std:          Desvios padrão das BB (padrão: 2.0)
        rsi_overbought:  Nível de sobrecompra (padrão: 70)
        rsi_oversold:    Nível de sobrevenda (padrão: 30)
        min_score:       Pontuação mínima para gerar sinal (padrão: 3)
        min_candles:     Mínimo de candles (padrão: 60)
    """

    def __init__(
        self,
        rsi_period: int = 14,
        ema_period: int = 50,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_overbought: int = 70,
        rsi_oversold: int = 30,
        min_score: int = 3,
        min_candles: int = 60,
    ):
        self.rsi_period = rsi_period
        self.ema_period = ema_period
        self.bb_period = bb_period
        self.bb_std = bb_std
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
            # RSI
            rsi_s = ta.rsi(df["close"], length=self.rsi_period)
            rsi = float(rsi_s.iloc[-1]) if rsi_s is not None else None

            # EMA
            ema_s = ta.ema(df["close"], length=self.ema_period)
            ema50 = float(ema_s.iloc[-1]) if ema_s is not None else None

            # MACD
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

            # Bollinger Bands
            bb_upper, bb_lower = None, None
            bb_df = ta.bbands(df["close"], length=self.bb_period, std=self.bb_std)
            if bb_df is not None and not bb_df.empty:
                uc = [c for c in bb_df.columns if "BBU" in c]
                lc = [c for c in bb_df.columns if "BBL" in c]
                if uc and lc:
                    bb_upper = float(bb_df[uc[0]].iloc[-1])
                    bb_lower = float(bb_df[lc[0]].iloc[-1])

            price = float(df["close"].iloc[-1])
            price_vs_ema = self._price_vs_ema(price, ema50)
            price_vs_bb  = self._price_vs_bb(price, bb_upper, bb_lower)

            signal, reason = self._generate_signal(
                rsi=rsi,
                macd_val=macd_val,
                macd_sig=macd_sig,
                macd_cross=macd_cross,
                price_vs_ema=price_vs_ema,
                price_vs_bb=price_vs_bb,
            )

            return TechnicalResult(
                signal=signal,
                reason=reason,
                rsi=round(rsi, 2) if rsi is not None else None,
                macd=round(macd_val, 4) if macd_val is not None else None,
                macd_signal=round(macd_sig, 4) if macd_sig is not None else None,
                macd_cross=macd_cross,
                ema50=round(ema50, 2) if ema50 is not None else None,
                bb_upper=round(bb_upper, 2) if bb_upper is not None else None,
                bb_lower=round(bb_lower, 2) if bb_lower is not None else None,
                current_price=round(price, 2),
                price_vs_ema=price_vs_ema,
                price_vs_bb=price_vs_bb,
            )

        except Exception as e:
            logger.error(f"Erro na análise técnica: {e}")
            return TechnicalResult(signal="AGUARDAR", reason=f"Erro interno: {e}")

    def _generate_signal(self, rsi, macd_val, macd_sig, macd_cross, price_vs_ema, price_vs_bb):
        """
        Scoring 4 indicadores:
          CALL: RSI não sobrecomprado | MACD bullish | preço acima EMA | BB lower (pullback)
          PUT:  RSI não sobrevendido  | MACD bearish | preço abaixo EMA | BB upper (extensão)
        """
        call_reasons = []
        put_reasons  = []
        call_score = 0
        put_score  = 0

        # 1. RSI
        if rsi is not None:
            if rsi < self.rsi_overbought:
                call_score += 1
                call_reasons.append(f"RSI={rsi:.1f}<{self.rsi_overbought}")
            if rsi > self.rsi_oversold:
                put_score += 1
                put_reasons.append(f"RSI={rsi:.1f}>{self.rsi_oversold}")

        # 2. MACD (cruzamento OU posição relativa)
        if macd_val is not None and macd_sig is not None:
            if macd_cross == "UP" or macd_val > macd_sig:
                call_score += 1
                call_reasons.append("MACD bullish")
            if macd_cross == "DOWN" or macd_val < macd_sig:
                put_score += 1
                put_reasons.append("MACD bearish")

        # 3. EMA50
        if price_vs_ema == "ABOVE":
            call_score += 1
            call_reasons.append("Preço>EMA50")
        elif price_vs_ema == "BELOW":
            put_score += 1
            put_reasons.append("Preço<EMA50")

        # 4. Bollinger Bands
        if price_vs_bb == "LOWER":
            call_score += 1
            call_reasons.append("BB lower (pullback)")
        elif price_vs_bb == "UPPER":
            put_score += 1
            put_reasons.append("BB upper (extensão)")

        # Desempate: se ambos atingem min_score, vence o maior
        if call_score >= self.min_score and call_score > put_score:
            return "CALL", " | ".join(call_reasons)
        if put_score >= self.min_score and put_score > call_score:
            return "PUT", " | ".join(put_reasons)
        if call_score >= self.min_score and call_score == put_score:
            return "AGUARDAR", f"Empate CALL={call_score} PUT={put_score}"

        return "AGUARDAR", f"Score insuficiente (CALL={call_score} PUT={put_score} min={self.min_score})"

    @staticmethod
    def _price_vs_ema(price: float, ema: Optional[float]) -> str:
        if ema is None:
            return "UNKNOWN"
        diff = (price - ema) / ema
        if diff > 0.001:
            return "ABOVE"
        elif diff < -0.001:
            return "BELOW"
        return "AT"

    @staticmethod
    def _price_vs_bb(price: float, bb_upper: Optional[float], bb_lower: Optional[float]) -> str:
        if bb_upper is None or bb_lower is None:
            return "UNKNOWN"
        if price >= bb_upper:
            return "UPPER"
        elif price <= bb_lower:
            return "LOWER"
        return "MIDDLE"


if __name__ == "__main__":
    import logging
    import sys, os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
    logging.basicConfig(level=logging.INFO)

    from backend.market.binance_client import BinanceClient
    bc = BinanceClient()
    df = bc.get_candles(symbol="BTCUSDT", interval="5m", limit=100)

    analyzer = TechnicalAnalyzer()
    result = analyzer.analyze(df)

    print(f"\nSinal   : {result.signal}")
    print(f"Razão   : {result.reason}")
    print(f"RSI     : {result.rsi}")
    print(f"MACD    : {result.macd} | Signal: {result.macd_signal} | Cross: {result.macd_cross}")
    print(f"EMA50   : {result.ema50} | Preço vs EMA: {result.price_vs_ema}")
    print(f"BB      : {result.bb_lower} – {result.bb_upper} | Preço vs BB: {result.price_vs_bb}")
