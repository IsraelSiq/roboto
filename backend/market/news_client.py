import logging
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class NewsClient:
    """Cliente simples para buscar notícias usando NewsAPI ou similar."""

    def __init__(self, api_key: str, base_url: str = "https://newsapi.org/v2"):
        self.api_key = api_key
        self.base_url = base_url

    def _request(self, endpoint: str, params: dict) -> Optional[dict]:
        url = f"{self.base_url}/{endpoint}"
        headers = {"Authorization": self.api_key}
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Erro ao buscar notícias: {e}")
            return None

    def get_crypto_news(self, query: str = "bitcoin", language: str = "en") -> list[dict]:
        params = {
            "q": query,
            "language": language,
            "sortBy": "publishedAt",
            "pageSize": 20,
        }
        data = self._request("everything", params)
        if not data or "articles" not in data:
            return []

        articles = []
        for art in data["articles"]:
            published = art.get("publishedAt")
            try:
                dt = datetime.fromisoformat(published.replace("Z", "+00:00")) if published else None
            except Exception:
                dt = None

            articles.append(
                {
                    "source": art.get("source", {}).get("name"),
                    "title": art.get("title"),
                    "description": art.get("description"),
                    "url": art.get("url"),
                    "published_at": dt,
                }
            )
        return articles

    def sentiment_score(self, text: str) -> float:
        """Placeholder de score de sentimento (integração futura com modelo)."""
        return 0.0
