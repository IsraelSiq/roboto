"""
Roboto — Binance Client
Conexão com a Binance (testnet ou real) via python-binance.

Funcionalidades:
    - Conexão automática testnet/real via .env
    - ping()                     — valida conexão rapidamente
    - get_candles()              — últimos N candles
    - get_historical_candles()   — histórico para backtest (sempre API real)
    - get_price()                — preço atual
    - get_account_balance()      — saldo da conta

Modo testnet:
    BINANCE_TESTNET=true  — usa testnet.binance.vision (sandbox com USDT virtual)
    BINANCE_TESTNET=false — usa api.binance.com (real)

Obtendo keys testnet:
    1. Acesse https://testnet.binance.vision
    2. Login com GitHub
    3. Gere API Key em "API Management"
    4. Coloque no .env: BINANCE_API_KEY, BINANCE_SECRET, BINANCE_TESTNET=true
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

# Testnet tem poucos klines próprios — usamos o cliente público para candles
_TESTNET_BASE_URL = "https://testnet.binance.vision"


class BinanceClient:
    """
    Wrapper do python-binance com suporte a testnet e real.

    Variáveis de ambiente:
        BINANCE_API_KEY    — API Key
        BINANCE_SECRET     — Secret Key
        BINANCE_TESTNET    — 'true' para sandbox, 'false' para real (default: true)
    """

    def __init__(self):
        api_key    = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_SECRET")
        self.testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        if not api_key or not api_secret:
            raise ValueError(
                "BINANCE_API_KEY e BINANCE_SECRET devem estar no .env\n"
                "Testnet: https://testnet.binance.vision (login com GitHub)"
            )

        self.client = Client(api_key, api_secret, testnet=self.testnet)
        mode = "TESTNET (🧪 sandbox)" if self.testnet else "REAL (💸 dinheiro real!)"
        base = _TESTNET_BASE_URL if self.testnet else "https://api.binance.com"
        logger.info(f"BinanceClient inicializado [{mode}] — {base}")

        # Cliente público para candles históricos reais (testnet não tem histórico)
        self._public_client = Client("", "")

    # ----------------------------------------------------------
    # PING / STATUS
    # ----------------------------------------------------------

    def ping(self) -> bool:
        """
        Testa conectividade com a Binance. Retorna True se ok.
        Usado pelo smoke test e health check.
        """
        try:
            self.client.ping()
            return True
        except Exception as e:
            logger.error(f"Binance ping falhou: {e}")
            return False

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
        """
        Preço atual do par.
        Testnet retorna preços próximos do real (espelhado).
        """
        try:
            # Usa cliente público para preço mais confiável no testnet
            ticker = self._public_client.get_symbol_ticker(symbol=symbol)
            return float(ticker["price"])
        except BinanceAPIException as e:
            logger.error(f"Erro ao buscar preço de {symbol}: {e}")
            return None

    # ----------------------------------------------------------
    # CANDLES EM TEMPO REAL
    # ----------------------------------------------------------

    def get_candles(
        self,
        symbol:   str = "BTCUSDT",
        interval: str = "5m",
        limit:    int = 100,
    ) -> pd.DataFrame:
        """
        Retorna os últimos N candles.

        Estratégia:
          - Testnet  → usa cliente público (testnet klines são esparsos)
          - Real     → usa cliente autenticado

        Qualquer exceção (BinanceAPIException, ConnectionError, timeout, etc.)
        é capturada e retorna DataFrame vazio para não derrubar o loop do bot.
        """
        try:
            client = self._public_client if self.testnet else self.client
            raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)
            return self._parse_candles(raw)
        except Exception as e:
            logger.error(f"Erro ao buscar candles de {symbol}: {e}")
            return pd.DataFrame()

    # ----------------------------------------------------------
    # CANDLES HISTÓRICOS (sempre API real)
    # ----------------------------------------------------------

    def get_historical_candles(
        self,
        symbol:   str            = "BTCUSDT",
        interval: str            = "5m",
        start:    str            = "3 months ago UTC",
        end:      Optional[str]  = None,
    ) -> pd.DataFrame:
        """
        Candles históricos da API pública Binance (dados reais).
        Independe do modo testnet — testnet não tem histórico confiável.
        """
        try:
            logger.info(f"Buscando histórico: {symbol} {interval} desde '{start}'...")
            raw = self._public_client.get_historical_klines(
                symbol=symbol, interval=interval,
                start_str=start, end_str=end,
            )
            df = self._parse_candles(raw)
            if not df.empty:
                logger.info(f"  {len(df)} candles ({df['open_time'].iloc[0].date()} → {df['open_time'].iloc[-1].date()})")
            return df
        except BinanceAPIException as e:
            logger.error(f"Erro ao buscar histórico de {symbol}: {e}")
            return pd.DataFrame()

    # ----------------------------------------------------------
    # SALDO DA CONTA
    # ----------------------------------------------------------

    def get_account_balance(self, asset: str = "USDT") -> Optional[float]:
        """
        Saldo disponível do ativo na conta (testnet ou real).
        Testnet dá ~10.000 USDT virtual por padrão.
        """
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

        df = pd.DataFrame(raw, columns:[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        df["open_time"]  = pd.to_datetime(df["open_time"],  unit:"ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit:"ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        return df[["open_time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bc = BinanceClient()
    print(f"\nPing:        {bc.ping()}")
    print(f"Online:      {bc.is_online()}")
    price = bc.get_price('BTCUSDT')
    print(f"Preço BTC:   ${price:,.2f}")
    print(f"Saldo USDT:  ${bc.get_account_balance('USDT'):,.2f}")
    df = bc.get_candles(symbol:"BTCUSDT", interval:"5m", limit:5)
    print("\nÚltimos 5 candles BTCUSDT 5m:")
    print(df.to_string(index:False))
