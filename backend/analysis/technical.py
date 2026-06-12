import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TechnicalResult:
    signal: str
    reason: str
    rsi: float | None
    current_price: float | None
    ema50: float | None
    macd: float | None
    macd_signal: float | None
    bb_upper: float | None
    bb_lower: float | None
    atr: float | None
    price_vs_ema: str | None


class TechnicalAnalysis:
    """Conjunto de indicadores técnicos usados pelo robô."""

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    @staticmethod
    def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = TechnicalAnalysis.ema(series, fast)
        ema_slow = TechnicalAnalysis.ema(series, slow)
        macd_line = ema_fast - ema_slow
        signal_line = TechnicalAnalysis.ema(macd_line, signal)
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"]

        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr

    @staticmethod
    def bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0):
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = sma + num_std * std
        lower = sma - num_std * std
        return sma, upper, lower

    @staticmethod
    def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
        close = df["close"]

        df["ema_20"] = TechnicalAnalysis.ema(close, 20)
        df["ema_50"] = TechnicalAnalysis.ema(close, 50)
        df["rsi_14"] = TechnicalAnalysis.rsi(close, 14)

        macd_line, signal_line, hist = TechnicalAnalysis.macd(close)
        df["macd_line"] = macd_line
        df["macd_signal"] = signal_line
        df["macd_hist"] = hist

        df["atr_14"] = TechnicalAnalysis.atr(df, 14)

        sma, upper, lower = TechnicalAnalysis.bollinger_bands(close)
        df["bb_middle"] = sma
        df["bb_upper"] = upper
        df["bb_lower"] = lower

        return df

    @staticmethod
    def generate_signal(
        df: pd.DataFrame,
        sentiment: str = "positive",
        only_strong: bool = True,
        atr_multiplier: float = 1.5,
    ) -> pd.DataFrame:
        df = TechnicalAnalysis.add_indicators(df.copy())

        df["signal"] = 0
        df["strength"] = "weak"

        up_trend = df["ema_20"] > df["ema_50"]
        down_trend = df["ema_20"] < df["ema_50"]

        bullish_rsi = df["rsi_14"] > 55
        bearish_rsi = df["rsi_14"] < 45

        macd_cross_up = (df["macd_line"].shift(1) < df["macd_signal"].shift(1)) & (
            df["macd_line"] > df["macd_signal"]
        )
        macd_cross_down = (df["macd_line"].shift(1) > df["macd_signal"].shift(1)) & (
            df["macd_line"] < df["macd_signal"]
        )

        df.loc[up_trend & bullish_rsi & macd_cross_up, "signal"] = 1
        df.loc[down_trend & bearish_rsi & macd_cross_down, "signal"] = -1

        df.loc[df["signal"] != 0, "strength"] = "strong"

        upper = df["bb_upper"]
        lower = df["bb_lower"]

        price = df["close"]
        near_upper = price > upper * 0.99
        near_lower = price < lower * 1.01

        df.loc[near_lower & (df["signal"] == 0) & up_trend, "signal"] = 1
        df.loc[near_upper & (df["signal"] == 0) & down_trend, "signal"] = -1

        if sentiment == "positive":
            df.loc[df["signal"] < 0, "signal"] = 0
        elif sentiment == "negative":
            df.loc[df["signal"] > 0, "signal"] = 0

        if only_strong:
            df.loc[df["strength"] != "strong", "signal"] = 0

        df["atr_stop"] = df["atr_14"] * atr_multiplier

        return df
