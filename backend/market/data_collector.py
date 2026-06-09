"""
Roboto — Data Collector
Coleta dados em paralelo: candles (Binance) + notícias (NewsAPI).

Arquitetura:
    - Thread 1: candles OHLCV a cada `candle_interval` segundos
    - Thread 2: notícias a cada `news_interval` segundos
    - Dados compartilhados via dicionário thread-safe com Lock

Uso:
    collector = DataCollector(symbol="BTCUSDT")
    collector.start()
    data = collector.get_latest()
    collector.stop()
"""

import logging
import threading
import time
from typing import Optional

import pandas as pd
from newsapi import NewsApiClient
import os
from dotenv import load_dotenv

from backend.market.binance_client import BinanceClient
from backend.market.symbols import SYMBOL_KEYWORDS

load_dotenv()
logger = logging.getLogger(__name__)


class DataCollector:
    """
    Coleta candles e notícias em threads paralelas.

    Args:
        symbol:          Par de trading (ex: 'BTCUSDT')
        interval:        Timeframe dos candles (ex: '5m')
        candle_limit:    Quantidade de candles a manter em memória
        candle_interval: Segundos entre cada coleta de candles
        news_interval:   Segundos entre cada coleta de notícias
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "5m",
        candle_limit: int = 100,
        candle_interval: int = 30,
        news_interval: int = 300,
    ):
        self.symbol = symbol
        self.interval = interval
        self.candle_limit = candle_limit
        self.candle_interval = candle_interval
        self.news_interval = news_interval

        self._binance = BinanceClient()
        self._newsapi = NewsApiClient(api_key=os.getenv("NEWSAPI_KEY"))
        self._keywords = SYMBOL_KEYWORDS.get(symbol, symbol.replace("USDT", ""))

        self._lock = threading.Lock()
        self._data = {
            "candles": pd.DataFrame(),
            "news": [],
            "price": None,
            "last_candle_update": None,
            "last_news_update": None,
        }

        self._running = False
        self._threads: list[threading.Thread] = []

    # ----------------------------------------------------------
    # CONTROLE
    # ----------------------------------------------------------

    def start(self):
        """Inicia as duas threads de coleta."""
        if self._running:
            logger.warning("DataCollector já está rodando.")
            return

        self._running = True

        t_candles = threading.Thread(target=self._candle_loop, daemon=True, name="CandleThread")
        t_news = threading.Thread(target=self._news_loop, daemon=True, name="NewsThread")

        self._threads = [t_candles, t_news]
        t_candles.start()
        t_news.start()

        logger.info(f"DataCollector iniciado — {self.symbol} {self.interval}")

    def stop(self):
        """Para as threads de coleta."""
        self._running = False
        logger.info("DataCollector parado.")

    # ----------------------------------------------------------
    # ACESSO AOS DADOS
    # ----------------------------------------------------------

    def get_latest(self) -> dict:
        """Retorna snapshot thread-safe dos dados mais recentes."""
        with self._lock:
            return {
                "candles": self._data["candles"].copy() if not self._data["candles"].empty else pd.DataFrame(),
                "news": list(self._data["news"]),
                "price": self._data["price"],
                "last_candle_update": self._data["last_candle_update"],
                "last_news_update": self._data["last_news_update"],
            }

    def get_candles(self) -> pd.DataFrame:
        """Retorna apenas os candles mais recentes."""
        with self._lock:
            return self._data["candles"].copy()

    def get_news(self) -> list:
        """Retorna apenas as notícias mais recentes."""
        with self._lock:
            return list(self._data["news"])

    def get_price(self) -> Optional[float]:
        """Retorna o preço atual."""
        with self._lock:
            return self._data["price"]

    # ----------------------------------------------------------
    # THREADS INTERNAS
    # ----------------------------------------------------------

    def _candle_loop(self):
        """Thread 1: coleta candles e preço a cada `candle_interval` segundos."""
        logger.info(f"[CandleThread] Iniciada — intervalo: {self.candle_interval}s")
        while self._running:
            try:
                df = self._binance.get_candles(
                    symbol=self.symbol,
                    interval=self.interval,
                    limit=self.candle_limit
                )
                price = self._binance.get_price(self.symbol)

                with self._lock:
                    self._data["candles"] = df
                    self._data["price"] = price
                    self._data["last_candle_update"] = time.time()

                logger.debug(f"[CandleThread] {len(df)} candles atualizados. Preço: ${price:,.2f}")

            except Exception as e:
                logger.error(f"[CandleThread] Erro: {e}")

            time.sleep(self.candle_interval)

    def _news_loop(self):
        """Thread 2: coleta notícias a cada `news_interval` segundos."""
        logger.info(f"[NewsThread] Iniciada — intervalo: {self.news_interval}s")
        while self._running:
            try:
                resp = self._newsapi.get_top_headlines(
                    q=self._keywords,
                    language="en",
                    page_size=10
                )

                if resp.get("status") == "ok":
                    articles = resp.get("articles", [])
                    news = [
                        {
                            "title": a.get("title", ""),
                            "description": a.get("description", ""),
                            "source": a.get("source", {}).get("name", ""),
                            "url": a.get("url", ""),
                            "published_at": a.get("publishedAt", ""),
                        }
                        for a in articles
                        if a.get("title")
                    ]

                    with self._lock:
                        self._data["news"] = news
                        self._data["last_news_update"] = time.time()

                    logger.debug(f"[NewsThread] {len(news)} notícias coletadas para '{self._keywords}'")

            except Exception as e:
                logger.error(f"[NewsThread] Erro: {e}")

            time.sleep(self.news_interval)


# ----------------------------------------------------------
# Teste rápido
# ----------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    collector = DataCollector(
        symbol="BTCUSDT",
        interval="5m",
        candle_limit=10,
        candle_interval=10,
        news_interval=30,
    )

    collector.start()
    print("\nColetando dados por 15 segundos...")
    time.sleep(15)

    data = collector.get_latest()
    print(f"\nPreço atual: ${data['price']:,.2f}")
    print(f"Candles recebidos: {len(data['candles'])}")
    print(f"Notícias recebidas: {len(data['news'])}")
    if data["news"]:
        print(f"\nPrimeira notícia: {data['news'][0]['title']}")

    collector.stop()
    print("\nDataCollector parado.")
