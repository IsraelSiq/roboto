"""
Roboto — News Client
Busca notícias de criptomoedas de fontes gratuitas sem API key.

Fontes (em ordem de tentativa):
    1. CryptoPanic public API  — JSON, sem auth, até 50 resultados
    2. CoinTelegraph RSS       — XML fallback caso CryptoPanic falhe
    3. CoinDesk RSS            — segundo fallback

Uso:
    client = NewsClient()
    news = client.get_news(keyword="bitcoin", limit=10)
    # news = [{'title': '...', 'description': '...'}, ...]
"""

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_CRYPTOPANIC_URL = "https://cryptopanic.com/api/free/v1/posts/"
_COINTELEGRAPH_RSS = "https://cointelegraph.com/rss"
_COINDESK_RSS = "https://www.coindesk.com/arc/outboundfeeds/rss/"

_REQUEST_TIMEOUT = 8  # segundos
_CACHE_TTL = 300       # 5 minutos


class NewsClient:
    """
    Busca notícias de criptomoedas sem necessidade de API key.

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
            keyword: Palavra-chave (ex: 'bitcoin', 'ethereum')
            limit:   Máximo de notícias a retornar

        Returns:
            Lista de dicts com 'title' e 'description'
        """
        cache_key = f"{keyword}:{limit}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.debug(f"[NewsClient] Cache hit para '{keyword}'")
            return cached

        news = self._fetch_cryptopanic(keyword, limit)

        if not news:
            logger.warning(f"[NewsClient] CryptoPanic falhou para '{keyword}', tentando CoinTelegraph RSS")
            news = self._fetch_rss(_COINTELEGRAPH_RSS, keyword, limit)

        if not news:
            logger.warning(f"[NewsClient] CoinTelegraph falhou, tentando CoinDesk RSS")
            news = self._fetch_rss(_COINDESK_RSS, keyword, limit)

        if not news:
            logger.warning(f"[NewsClient] Todas as fontes falharam para '{keyword}' — retornando lista vazia")

        self._set_cache(cache_key, news)
        logger.info(f"[NewsClient] {len(news)} notícias obtidas para '{keyword}'")
        return news

    # ----------------------------------------------------------
    # FONTES
    # ----------------------------------------------------------

    def _fetch_cryptopanic(self, keyword: str, limit: int) -> list[dict]:
        """Busca na CryptoPanic public API (sem auth)."""
        try:
            params = {
                "public": "true",
                "kind": "news",
                "filter": "hot",
                "currencies": self._keyword_to_currency(keyword),
            }
            resp = requests.get(
                _CRYPTOPANIC_URL,
                params=params,
                timeout=_REQUEST_TIMEOUT,
                headers={"User-Agent": "Roboto/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            news = []
            for item in results[:limit]:
                title = item.get("title", "").strip()
                if title:
                    news.append({"title": title, "description": ""})

            logger.debug(f"[NewsClient] CryptoPanic: {len(news)} notícias para '{keyword}'")
            return news

        except Exception as e:
            logger.warning(f"[NewsClient] CryptoPanic erro: {e}")
            return []

    def _fetch_rss(self, url: str, keyword: str, limit: int) -> list[dict]:
        """Busca em feed RSS e filtra por keyword."""
        try:
            resp = requests.get(
                url,
                timeout=_REQUEST_TIMEOUT,
                headers={"User-Agent": "Roboto/1.0"},
            )
            resp.raise_for_status()

            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.content)

            news = []
            kw_lower = keyword.lower()
            for item in root.iter("item"):
                title_el = item.find("title")
                desc_el = item.find("description")
                title = (title_el.text or "").strip() if title_el is not None else ""
                desc = (desc_el.text or "").strip() if desc_el is not None else ""

                # Filtra por keyword se possível
                combined = f"{title} {desc}".lower()
                if kw_lower not in combined and not self._is_generic_crypto_keyword(kw_lower):
                    continue

                if title:
                    news.append({"title": title, "description": desc[:200]})

                if len(news) >= limit:
                    break

            # Se keyword muito específico não retornou nada, pega os primeiros sem filtro
            if not news:
                for item in root.iter("item"):
                    title_el = item.find("title")
                    desc_el = item.find("description")
                    title = (title_el.text or "").strip() if title_el is not None else ""
                    desc = (desc_el.text or "").strip() if desc_el is not None else ""
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
    def _keyword_to_currency(keyword: str) -> str:
        """Mapeia keyword para código de moeda do CryptoPanic."""
        mapping = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "solana": "SOL",
            "bnb": "BNB",
            "binance coin": "BNB",
            "xrp": "XRP",
            "ripple": "XRP",
            "cardano": "ADA",
            "dogecoin": "DOGE",
            "avalanche": "AVAX",
            "polkadot": "DOT",
        }
        return mapping.get(keyword.lower(), "BTC")

    @staticmethod
    def _is_generic_crypto_keyword(keyword: str) -> bool:
        """Retorna True para keywords genéricas que aparecem em qualquer notícia cripto."""
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
    import logging
    logging.basicConfig(level=logging.DEBUG)

    client = NewsClient()

    for kw in ["bitcoin", "ethereum", "solana"]:
        print(f"\n{'='*50}")
        print(f"  Keyword: {kw}")
        news = client.get_news(keyword=kw, limit=5)
        for i, n in enumerate(news, 1):
            print(f"  {i}. {n['title'][:80]}")
        print(f"  Total: {len(news)} notícias")
