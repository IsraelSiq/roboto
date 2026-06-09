"""
Roboto — Backtest Data Loader
Baixa candles históricos da Binance para uso no backtest.

Uso:
    loader = BacktestDataLoader()
    df = loader.load(symbol="BTCUSDT", interval="5m", start="2026-01-01", end="2026-06-01")
"""

import logging

import pandas as pd

from backend.market.binance_client import BinanceClient

logger = logging.getLogger(__name__)


class BacktestDataLoader:
    """
    Baixa candles históricos da Binance via get_historical_candles().
    Utiliza a biblioteca python-binance que já faz a paginação automática.
    """

    def __init__(self):
        self.client = BinanceClient()

    def load(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "5m",
        start: str = "2026-01-01",
        end: str = None,
    ) -> pd.DataFrame:
        """
        Baixa todos os candles entre start e end.

        Args:
            symbol:   Par de trading (ex: BTCUSDT)
            interval: Timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            start:    Data inicial (YYYY-MM-DD)
            end:      Data final (YYYY-MM-DD). Default: agora.

        Returns:
            DataFrame com colunas: open_time, open, high, low, close, volume
        """
        logger.info(f"[DataLoader] Baixando {symbol} {interval} de {start} até {end or 'agora'}...")

        df = self.client.get_historical_candles(
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
        )

        if df.empty:
            logger.warning("[DataLoader] Nenhum candle retornado.")
            return df

        df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)
        logger.info(f"[DataLoader] {len(df):,} candles carregados ({df['open_time'].iloc[0].date()} → {df['open_time'].iloc[-1].date()}).")
        return df
