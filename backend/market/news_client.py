"""
Roboto — News Client
Busca notícias de criptomoedas via feeds RSS gratuitos, sem API key.

Fontes (em ordem de tentativa):
    1. CoinTelegraph RSS
    2. CoinDesk RSS
    3. Decrypt RSS
    4. Bitcoin Magazine RSS

Uso:
    client = NewsClient()
    news = client.get_news(keyword="bitcoin", limit=10)
    # news = [{'title': '...', 'description': '...'}, ...]
"""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_RSS_SOURCES = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/",
]

_REQUEST_TIMEOUT = 8
_CACHE_TTL = 300  # 5 minutos


class NewsClient:
    """
    Busca notícias de criptomoedas via RSS, sem API key.

    Args:
        cache_ttl: Tempo de vida do cache em segundos (padrão: 300)
    """

    def __init__(self, cache_ttl: int = _CACHE_TTL):
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[list, float]] = {}

    # ----------------------------------------------------------
    # MÉTODO PRINCIPAL
    # ----------------------------------------------------------

    def get_news(self, keyword: str = "bitcoin", limit: int = 10) -> list[dict]:
        """
        Retorna lista de notícias para o keyword fornecido.

        Args:
            keyword: Palavra-chave (ex: 'bitcoin', 'bnb')
            limit:   Máximo de notícias a retornar

        Returns:
            Lista de dicts com 'title' e 'description'
        """
        cache_key = f"{keyword}:{limit}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.debug(f"[NewsClient] Cache hit para '{keyword}'")
            return cached

        news = []
        for url in _RSS_SOURCES:
            if len(news) >= limit:
                break
            fetched = self._fetch_rss(url, keyword, limit - len(news))
            news.extend(fetched)

        if not news:
            logger.warning(f"[NewsClient] Todas as fontes RSS falharam para '{keyword}'")

        news = news[:limit]
        self._set_cache(cache_key, news)
        logger.info(f"[NewsClient] {len(news)} notícias obtidas para '{keyword}'")
        return news

    # ----------------------------------------------------------
    # FONTE
    # ----------------------------------------------------------

    def _fetch_rss(self, url: str, keyword: str, limit: int) -> list[dict]:
        """Busca em feed RSS e filtra por keyword."""
        try:
            resp = requests.get(
                url,
                timeout=_REQUEST_TIMEOUT,
                headers={"User-Agent": "Roboto/1.0"},
            )
            resp.raise_for_status()

            root = ET.fromstring(resp.content)
            kw_lower = keyword.lower()
            is_generic = self._is_generic_crypto_keyword(kw_lower)

            news = []
            for item in root.iter("item"):
                title_el = item.find("title")
                desc_el  = item.find("description")
                title = (title_el.text or "").strip() if title_el is not None else ""
                desc  = (desc_el.text  or "").strip() if desc_el  is not None else ""

                combined = f"{title} {desc}".lower()
                if not is_generic and kw_lower not in combined:
                    continue

                if title:
                    news.append({"title": title, "description": desc[:200]})

                if len(news) >= limit:
                    break

            # Keyword muito específico não retornou nada — pega primeiros sem filtro
            if not news:
                for item in root.iter("item"):
                    title_el = item.find("title")
                    desc_el  = item.find("description")
                    title = (title_el.text or "").strip() if title_el is not None else ""
                    desc  = (desc_el.text  or "").strip() if desc_el  is not None else ""
                    if title:
                        news.append({"title": title, "description": desc[:200]})
                    if len(news) >= limit:
                        break

            logger.debug(f"[NewsClient] RSS {url}: {len(news)} notícias")
            return news

        except Exception as e:
            logger.warning(f"[NewsClient] RSS {url} erro: {e}")
            return []

    # ----------------------------------------------------------
    # HELPERS
    # ----------------------------------------------------------

    @staticmethod
    def _is_generic_crypto_keyword(keyword: str) -> bool:
        generic = {"crypto", "cryptocurrency", "blockchain", "defi", "web3", "altcoin"}
        return keyword in generic

    def _get_cache(self, key: str) -> Optional[list]:
        if key in self._cache:
            result, ts = self._cache[key]
            if time.time() - ts < self.cache_ttl:
                return result
            del self._cache[key]
        return None

    def _set_cache(self, key: str, result: list):
        self._cache[key] = (result, time.time())


# ----------------------------------------------------------
# Teste rápido
# ----------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    client = NewsClient()
    for kw in ["bitcoin", "bnb", "ethereum"]:
        print(f"\n{'='*50}  Keyword: {kw}")
        news = client.get_news(keyword=kw, limit=5)
        for i, n in enumerate(news, 1):
            print(f"  {i}. {n['title'][:80]}")
        print(f"  Total: {len(news)} notícias")
