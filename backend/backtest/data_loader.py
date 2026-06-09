"""
Roboto — Backtest Data Loader
Baixa candles históricos da Binance para uso no backtest.

Uso:
    loader = BacktestDataLoader()
    df = loader.load(symbol="BTCUSDT", interval="5m", start="2026-01-01", end="2026-06-01")
"""

import logging
import time
from datetime import datetime, timezone

import pandas as pd

from backend.market.binance_client import BinanceClient

logger = logging.getLogger(__name__)


class BacktestDataLoader:
    """
    Baixa candles históricos da Binance em lotes de 1000.
    A API da Binance limita 1000 candles por request.
    """

    LIMIT_PER_REQUEST = 1000

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
        start_ms = self._to_ms(start)
        end_ms = self._to_ms(end) if end else int(time.time() * 1000)

        logger.info(f"[DataLoader] Baixando {symbol} {interval} de {start} até {end or 'agora'}...")

        all_candles = []
        current_start = start_ms

        while current_start < end_ms:
            try:
                df = self.client.get_candles(
                    symbol=symbol,
                    interval=interval,
                    limit=self.LIMIT_PER_REQUEST,
                    start_time=current_start,
                    end_time=end_ms,
                )
            except Exception as e:
                logger.error(f"[DataLoader] Erro ao buscar candles: {e}")
                break

            if df.empty:
                break

            all_candles.append(df)
            last_time = int(df["open_time"].iloc[-1].timestamp() * 1000)

            if len(df) < self.LIMIT_PER_REQUEST:
                break

            # Avança para o próximo lote (1 ms depois do último candle)
            current_start = last_time + 1
            time.sleep(0.1)  # respeita rate limit da Binance

        if not all_candles:
            logger.warning("[DataLoader] Nenhum candle retornado.")
            return pd.DataFrame()

        result = pd.concat(all_candles, ignore_index=True)
        result = result.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)

        logger.info(f"[DataLoader] {len(result)} candles carregados.")
        return result

    @staticmethod
    def _to_ms(date_str: str) -> int:
        """Converte string YYYY-MM-DD para timestamp em milissegundos."""
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
