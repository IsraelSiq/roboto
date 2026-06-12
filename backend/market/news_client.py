"""
Roboto — News Client
Busca notícias de criptomoedas via cryptocurrency.cv (primário) e RSS (fallback).

Fontes (em ordem de tentativa):
    1. cryptocurrency.cv — API gratuita, sem API key, +662k artigos históricos
    2. CoinTelegraph RSS
    3. CoinDesk RSS
    4. Decrypt RSS
    5. Bitcoin Magazine RSS

Uso:
    client = NewsClient()
    news = client.get_news(keyword="bnb", limit=10)
    # news = [{'title': '...', 'description': '...', 'published_at': '...', 'source': '...'}, ...]

    # Busca histórica (para backfill do NewsImpactCollector)
    history = client.get_historical_news("bnb", from_date="2026-05-01", to_date="2026-05-31")
"""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_CRYPTOCURRENCY_CV_URL = "https://cryptocurrency.cv/api/news"

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
    Busca notícias de criptomoedas via cryptocurrency.cv + RSS fallback.

    Cada notícia retornada inclui:
        title        : manchete
        description  : resumo (até 200 chars)
        published_at : ISO 8601 timestamp (ou None se RSS sem data)
        source       : nome da fonte (ex: 'CoinDesk')

    Args:
        cache_ttl: Tempo de vida do cache em segundos (padrão: 300)
    """

    def __init__(self, cache_ttl: int = _CACHE_TTL):
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[list, float]] = {}

    # ----------------------------------------------------------
    # MÉTODO PRINCIPAL
    # ----------------------------------------------------------

    def get_news(self, keyword: str = "bnb", limit: int = 10) -> list[dict]:
        """
        Retorna lista de notícias para o keyword fornecido.
        Tenta cryptocurrency.cv primeiro, depois RSS.

        Args:
            keyword: Palavra-chave (ex: 'bnb', 'bitcoin')
            limit:   Máximo de notícias a retornar

        Returns:
            Lista de dicts com title, description, published_at, source
        """
        cache_key = f"{keyword}:{limit}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.debug(f"[NewsClient] Cache hit para '{keyword}'")
            return cached

        # Tenta cryptocurrency.cv primeiro
        news = self._fetch_cryptocurrency_cv(keyword, limit)

        # Fallback para RSS se cryptocurrency.cv não retornou nada
        if not news:
            logger.info(f"[NewsClient] cryptocurrency.cv sem resultado — tentando RSS para '{keyword}'")
            for url in _RSS_SOURCES:
                if len(news) >= limit:
                    break
                fetched = self._fetch_rss(url, keyword, limit - len(news))
                news.extend(fetched)

        if not news:
            logger.warning(f"[NewsClient] Todas as fontes falharam para '{keyword}'")

        news = news[:limit]
        self._set_cache(cache_key, news)
        logger.info(f"[NewsClient] {len(news)} notícias obtidas para '{keyword}'")
        return news

    def get_historical_news(
        self,
        keyword: str,
        from_date: str,
        to_date: str,
        limit: int = 100,
    ) -> list[dict]:
        """
        Busca notícias históricas via cryptocurrency.cv por intervalo de datas.
        Usado pelo NewsImpactCollector para backfill de dados históricos.

        Args:
            keyword:   Palavra-chave (ex: 'bnb')
            from_date: Data início no formato YYYY-MM-DD
            to_date:   Data fim no formato YYYY-MM-DD
            limit:     Máximo de resultados (padrão: 100)

        Returns:
            Lista de dicts com title, description, published_at, source
        """
        try:
            params = {
                "q":     keyword,
                "from":  from_date,
                "to":    to_date,
                "limit": limit,
            }
            resp = requests.get(
                _CRYPTOCURRENCY_CV_URL,
                params=params,
                timeout=_REQUEST_TIMEOUT,
                headers={"User-Agent": "Roboto/1.0"},
            )
            resp.raise_for_status()
            items = resp.json().get("data", [])
            news = self._parse_cryptocurrency_cv_items(items, limit)
            logger.info(
                f"[NewsClient] Histórico '{keyword}' {from_date}→{to_date}: "
                f"{len(news)} notícias"
            )
            return news
        except Exception as e:
            logger.warning(f"[NewsClient] Histórico cryptocurrency.cv falhou: {e}")
            return []

    # ----------------------------------------------------------
    # FONTES
    # ----------------------------------------------------------

    def _fetch_cryptocurrency_cv(self, keyword: str, limit: int) -> list[dict]:
        """
        Busca notícias recentes em cryptocurrency.cv (sem API key).

        Args:
            keyword: Palavra-chave para busca
            limit:   Máximo de resultados

        Returns:
            Lista de dicts com title, description, published_at, source
        """
        try:
            params = {"q": keyword, "limit": limit}
            resp = requests.get(
                _CRYPTOCURRENCY_CV_URL,
                params=params,
                timeout=_REQUEST_TIMEOUT,
                headers={"User-Agent": "Roboto/1.0"},
            )
            resp.raise_for_status()
            items = resp.json().get("data", [])
            news = self._parse_cryptocurrency_cv_items(items, limit)
            logger.debug(
                f"[NewsClient] cryptocurrency.cv: {len(news)} notícias para '{keyword}'"
            )
            return news
        except Exception as e:
            logger.debug(f"[NewsClient] cryptocurrency.cv indisponível: {e}")
            return []

    @staticmethod
    def _parse_cryptocurrency_cv_items(items: list, limit: int) -> list[dict]:
        """Normaliza os items retornados pela API cryptocurrency.cv."""
        news = []
        for item in items:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            news.append({
                "title":        title,
                "description":  (item.get("description") or "")[:200],
                "published_at": item.get("published_at"),   # ISO 8601 ou None
                "source":       item.get("source", ""),
            })
            if len(news) >= limit:
                break
        return news

    def _fetch_rss(self, url: str, keyword: str, limit: int) -> list[dict]:
        """Busca em feed RSS e filtra por keyword. Fallback sem published_at preciso."""
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

            # Tenta identificar a fonte pelo URL
            source = url.split("/")[2].replace("www.", "").split(".")[0].capitalize()

            news = []
            for item in root.iter("item"):
                title_el   = item.find("title")
                desc_el    = item.find("description")
                pubdate_el = item.find("pubDate")

                title   = (title_el.text or "").strip() if title_el is not None else ""
                desc    = (desc_el.text or "").strip() if desc_el is not None else ""
                pub_raw = (pubdate_el.text or "").strip() if pubdate_el is not None else None

                combined = f"{title} {desc}".lower()
                if not is_generic and kw_lower not in combined:
                    continue

                if title:
                    news.append({
                        "title":        title,
                        "description":  desc[:200],
                        "published_at": pub_raw,   # RFC 2822, não ISO — converter se necessário
                        "source":       source,
                    })

                if len(news) >= limit:
                    break

            # Keyword muito específico não retornou nada — pega primeiros sem filtro
            if not news:
                for item in root.iter("item"):
                    title_el   = item.find("title")
                    desc_el    = item.find("description")
                    pubdate_el = item.find("pubDate")
                    title   = (title_el.text or "").strip() if title_el is not None else ""
                    desc    = (desc_el.text or "").strip() if desc_el is not None else ""
                    pub_raw = (pubdate_el.text or "").strip() if pubdate_el is not None else None
                    if title:
                        news.append({
                            "title":        title,
                            "description":  desc[:200],
                            "published_at": pub_raw,
                            "source":       source,
                        })
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
    for kw in ["bnb", "bitcoin", "ethereum"]:
        print(f"\n{'='*50}  Keyword: {kw}")
        news = client.get_news(keyword=kw, limit=5)
        for i, n in enumerate(news, 1):
            print(f"  {i}. [{n.get('source','?')}] {n['title'][:70]}")
            print(f"     published_at: {n.get('published_at')}")
        print(f"  Total: {len(news)} notícias")
