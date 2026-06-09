"""
Roboto — Análise Técnica
Calcul a RSI, EMA50, MACD e Bollinger Bands usando pandas-ta-classic.
Gera sinal técnico: CALL | PUT | AGUARDAR

Estr atégia:
    CALL  → RSI < 70 + MACD cruzou pra cima + preço acima da EMA50
    PUT   → RSI > 30 + MACD cruzou pra baixo + preço abaixo da EMA50
    AGUARDAR → demais casos (zona de indecisão)

Uso:
    from backend.analysis.technical import TechnicalAnalyzer
    ta = TechnicalAnalyzer()
    result = ta.analyze(df_candles)
    print(result.signal)   # CALL | PUT | AGUARDAR
    print(result.reason)   # explicação textual
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import pandas_ta_classic as ta

logger = logging.getLogger(__name__)


@dataclass
class TechnicalResult:
    """Resultado completo da análise técnica."""
    signal: str              # CALL | PUT | AGUARDAR
    reason: str              # explicação textual
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
    Analisador técnico com RSI, EMA50, MACD e Bollinger Bands.

    Args:
        rsi_period:       Período do RSI (padrão: 14)
        ema_period:       Período da EMA (padrão: 50)
        bb_period:        Período das Bollinger Bands (padrão: 20)
        bb_std:           Desvios padrão das Bollinger Bands (padrão: 2.0)
        rsi_overbought:   Nível de sobrecompra do RSI (padrão: 70)
        rsi_oversold:     Nível de sobrevenda do RSI (padrão: 30)
        min_candles:      Mínimo de candles necessários para análise (padrão: 60)
    """

    def __init__(
        self,
        rsi_period: int = 14,
        ema_period: int = 50,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_overbought: int = 70,
        rsi_oversold: int = 30,
        min_candles: int = 60,
    ):
        self.rsi_period = rsi_period
        self.ema_period = ema_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.min_candles = min_candles

    # ----------------------------------------------------------
    # MÉTODO PRINCIPAL
    # ----------------------------------------------------------

    def analyze(self, df: pd.DataFrame) -> TechnicalResult:
        """
        Analisa os candles e retorna TechnicalResult com sinal e métricas.

        Args:
            df: DataFrame com colunas open, high, low, close, volume

        Returns:
            TechnicalResult com signal, reason e todos os indicadores
        """
        if df.empty or len(df) < self.min_candles:
            return TechnicalResult(
                signal="AGUARDAR",
                reason=f"Candles insuficientes ({len(df)}/{self.min_candles} necessários)"
            )

        df = df.copy()

        try:
            # --- RSI ---
            rsi_series = ta.rsi(df["close"], length=self.rsi_period)
            rsi = float(rsi_series.iloc[-1]) if rsi_series is not None else None

            # --- EMA50 ---
            ema_series = ta.ema(df["close"], length=self.ema_period)
            ema50 = float(ema_series.iloc[-1]) if ema_series is not None else None

            # --- MACD ---
            macd_df = ta.macd(df["close"])
            macd_val, macd_sig, macd_cross = None, None, "NONE"
            if macd_df is not None and not macd_df.empty:
                cols = macd_df.columns.tolist()
                macd_col  = [c for c in cols if c.startswith("MACD_") and "s" not in c.lower() and "h" not in c.lower()]
                sig_col   = [c for c in cols if "MACDs" in c]
                if macd_col and sig_col:
                    macd_val = float(macd_df[macd_col[0]].iloc[-1])
                    macd_sig = float(macd_df[sig_col[0]].iloc[-1])
                    macd_prev = float(macd_df[macd_col[0]].iloc[-2])
                    sig_prev  = float(macd_df[sig_col[0]].iloc[-2])
                    if macd_prev <= sig_prev and macd_val > macd_sig:
                        macd_cross = "UP"
                    elif macd_prev >= sig_prev and macd_val < macd_sig:
                        macd_cross = "DOWN"

            # --- Bollinger Bands ---
            bb_df = ta.bbands(df["close"], length=self.bb_period, std=self.bb_std)
            bb_upper, bb_lower = None, None
            if bb_df is not None and not bb_df.empty:
                upper_col = [c for c in bb_df.columns if "BBU" in c]
                lower_col = [c for c in bb_df.columns if "BBL" in c]
                if upper_col and lower_col:
                    bb_upper = float(bb_df[upper_col[0]].iloc[-1])
                    bb_lower = float(bb_df[lower_col[0]].iloc[-1])

            # --- Preço atual ---
            price = float(df["close"].iloc[-1])

            # --- Posição relativa ---
            price_vs_ema = self._price_vs_ema(price, ema50)
            price_vs_bb  = self._price_vs_bb(price, bb_upper, bb_lower)

            # --- Sinal final ---
            signal, reason = self._generate_signal(
                rsi=rsi,
                macd_cross=macd_cross,
                price_vs_ema=price_vs_ema,
                price_vs_bb=price_vs_bb,
            )

            return TechnicalResult(
                signal=signal,
                reason=reason,
                rsi=round(rsi, 2) if rsi else None,
                macd=round(macd_val, 4) if macd_val else None,
                macd_signal=round(macd_sig, 4) if macd_sig else None,
                macd_cross=macd_cross,
                ema50=round(ema50, 2) if ema50 else None,
                bb_upper=round(bb_upper, 2) if bb_upper else None,
                bb_lower=round(bb_lower, 2) if bb_lower else None,
                current_price=round(price, 2),
                price_vs_ema=price_vs_ema,
                price_vs_bb=price_vs_bb,
            )

        except Exception as e:
            logger.error(f"Erro na análise técnica: {e}")
            return TechnicalResult(signal="AGUARDAR", reason=f"Erro interno: {e}")

    # ----------------------------------------------------------
    # LÓGICA DE SINAL
    # ----------------------------------------------------------

    def _generate_signal(self, rsi, macd_cross, price_vs_ema, price_vs_bb) -> tuple[str, str]:
        """
        Gera sinal CALL/PUT/AGUARDAR com base nos indicadores.

        Regras:
            CALL  → RSI < overbought + MACD cruzou UP + preço acima da EMA50
            PUT   → RSI > oversold   + MACD cruzou DOWN + preço abaixo da EMA50
            AGUARDAR → demais casos
        """
        reasons = []

        # --- CALL ---
        call_score = 0
        if rsi is not None and rsi < self.rsi_overbought:
            call_score += 1
            reasons.append(f"RSI={rsi:.1f} (não sobrecomprado)")
        if macd_cross == "UP":
            call_score += 1
            reasons.append("MACD cruzou pra cima")
        if price_vs_ema == "ABOVE":
            call_score += 1
            reasons.append("Preço acima da EMA50")

        # --- PUT ---
        put_score = 0
        if rsi is not None and rsi > self.rsi_oversold:
            put_score += 1
        if macd_cross == "DOWN":
            put_score += 1
            reasons.append("MACD cruzou pra baixo")
        if price_vs_ema == "BELOW":
            put_score += 1
            reasons.append("Preço abaixo da EMA50")

        # Sinal forte exige os 3 critérios
        if call_score == 3:
            return "CALL", " | ".join(reasons)
        if put_score == 3:
            return "PUT", " | ".join(reasons) if reasons else "RSI alto + MACD pra baixo + abaixo da EMA50"

        # Sinal fraco (2 critérios) ainda gera sinal, mas com aviso
        if call_score == 2 and macd_cross == "UP":
            return "CALL", "Sinal fraco (2/3): " + " | ".join(reasons)
        if put_score == 2 and macd_cross == "DOWN":
            return "PUT", "Sinal fraco (2/3): MACD pra baixo + " + ("abaixo da EMA50" if price_vs_ema == "BELOW" else f"RSI={rsi:.1f}")

        return "AGUARDAR", f"Critérios insuficientes (CALL={call_score}/3, PUT={put_score}/3)"

    # ----------------------------------------------------------
    # HELPERS
    # ----------------------------------------------------------

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


# ----------------------------------------------------------
# Teste rápido
# ----------------------------------------------------------
if __name__ == "__main__":
    import logging
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

    logging.basicConfig(level=logging.INFO)

    from backend.market.binance_client import BinanceClient

    bc = BinanceClient()
    df = bc.get_candles(symbol="BTCUSDT", interval="5m", limit=100)
    print(f"Candles recebidos: {len(df)}")

    analyzer = TechnicalAnalyzer()
    result = analyzer.analyze(df)

    print(f"\n{'='*45}")
    print(f"Sinal t\u00e9cnico : {result.signal}")
    print(f"Raz\u00e3o         : {result.reason}")
    print(f"{'='*45}")
    print(f"Pre\u00e7o atual   : ${result.current_price:,.2f}")
    print(f"RSI           : {result.rsi}")
    print(f"EMA50         : ${result.ema50:,.2f}")
    print(f"Pre\u00e7o vs EMA  : {result.price_vs_ema}")
    print(f"MACD          : {result.macd}")
    print(f"MACD Signal   : {result.macd_signal}")
    print(f"MACD Cross    : {result.macd_cross}")
    print(f"BB Upper      : ${result.bb_upper:,.2f}")
    print(f"BB Lower      : ${result.bb_lower:,.2f}")
    print(f"Pre\u00e7o vs BB   : {result.price_vs_bb}")
