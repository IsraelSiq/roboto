"""
Roboto — Binance Client
Conexão com a Binance (testnet ou real) via python-binance.

Funcionalidades:
    - Conexão automática testnet/real via .env
    - get_candles()              — últimos N candles (testnet/real)
    - get_historical_candles()   — histórico para backtest (sempre API real)
    - get_price()                — preço atual
    - get_account_balance()      — saldo da conta
"""

import os
import logging
from typing import Optional

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class BinanceClient:
    """
    Wrapper do python-binance com suporte a testnet e real.
    Configuração via variáveis de ambiente:
        BINANCE_API_KEY    — API Key
        BINANCE_SECRET     — Secret Key
        BINANCE_TESTNET    — 'true' para testnet, 'false' para real
    """

    def __init__(self):
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_SECRET")
        self.testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        if not api_key or not api_secret:
            raise ValueError("BINANCE_API_KEY e BINANCE_SECRET devem estar no .env")

        self.client = Client(api_key, api_secret, testnet=self.testnet)
        mode = "TESTNET" if self.testnet else "REAL"
        logger.info(f"BinanceClient inicializado [{mode}]")

        # Cliente público (sem testnet) para dados históricos reais
        self._public_client = Client("", "")

    # ----------------------------------------------------------
    # STATUS
    # ----------------------------------------------------------

    def is_online(self) -> bool:
        try:
            status = self.client.get_system_status()
            return status.get("status") == 0
        except Exception as e:
            logger.error(f"Erro ao checar status Binance: {e}")
            return False

    # ----------------------------------------------------------
    # PREÇO ATUAL
    # ----------------------------------------------------------

    def get_price(self, symbol: str = "BTCUSDT") -> Optional[float]:
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker["price"])
        except BinanceAPIException as e:
            logger.error(f"Erro ao buscar preço de {symbol}: {e}")
            return None

    # ----------------------------------------------------------
    # CANDLES EM TEMPO REAL (testnet/real)
    # ----------------------------------------------------------

    def get_candles(self, symbol: str = "BTCUSDT", interval: str = "5m", limit: int = 100) -> pd.DataFrame:
        """
        Retorna os últimos N candles do servidor configurado (testnet ou real).
        """
        try:
            raw = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
            return self._parse_candles(raw)
        except BinanceAPIException as e:
            logger.error(f"Erro ao buscar candles de {symbol}: {e}")
            return pd.DataFrame()

    # ----------------------------------------------------------
    # CANDLES HISTÓRICOS (sempre API real — testnet não tem histórico)
    # ----------------------------------------------------------

    def get_historical_candles(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "5m",
        start: str = "3 months ago UTC",
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Retorna candles históricos da API pública da Binance (dados reais).
        Usa o cliente público independente do modo testnet/real configurado,
        pois o testnet não possui dados históricos confiáveis.

        Args:
            symbol:   Par de trading (ex: 'BTCUSDT')
            interval: Timeframe (ex: '5m', '1h')
            start:    Data de início (ex: '2026-01-01' ou '3 months ago UTC')
            end:      Data de fim (padrão: agora)

        Returns:
            DataFrame com colunas: open_time, open, high, low, close, volume
        """
        try:
            logger.info(f"Buscando candles históricos (API real): {symbol} {interval} desde '{start}'...")
            raw = self._public_client.get_historical_klines(
                symbol=symbol,
                interval=interval,
                start_str=start,
                end_str=end,
            )
            df = self._parse_candles(raw)
            if df.empty:
                return df
            logger.info(f"  {len(df)} candles recebidos ({df['open_time'].iloc[0].date()} → {df['open_time'].iloc[-1].date()})")
            return df
        except BinanceAPIException as e:
            logger.error(f"Erro ao buscar histórico de {symbol}: {e}")
            return pd.DataFrame()

    # ----------------------------------------------------------
    # SALDO DA CONTA
    # ----------------------------------------------------------

    def get_account_balance(self, asset: str = "USDT") -> Optional[float]:
        try:
            account = self.client.get_account()
            for balance in account["balances"]:
                if balance["asset"] == asset:
                    return float(balance["free"])
            return 0.0
        except BinanceAPIException as e:
            logger.error(f"Erro ao buscar saldo de {asset}: {e}")
            return None

    # ----------------------------------------------------------
    # HELPER INTERNO
    # ----------------------------------------------------------

    @staticmethod
    def _parse_candles(raw: list) -> pd.DataFrame:
        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])

        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        return df[["open_time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    bc = BinanceClient()
    print(f"\nOnline: {bc.is_online()}")
    print(f"Preço BTC: ${bc.get_price('BTCUSDT'):,.2f}")
    print(f"Saldo USDT: ${bc.get_account_balance('USDT'):,.2f}")

    df = bc.get_candles(symbol="BTCUSDT", interval="5m", limit=5)
    print(f"\nÚltimos 5 candles BTCUSDT 5m (testnet):")
    print(df.to_string(index=False))

    df2 = bc.get_historical_candles(symbol="BTCUSDT", interval="1h", start="3 days ago UTC")
    print(f"\nÚltimos 3 dias BTCUSDT 1h (API real): {len(df2)} candles")
    print(df2.tail(3).to_string(index=False))
