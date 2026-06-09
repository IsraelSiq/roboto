"""
Roboto — Sentiment Analysis
Classifica notícias financeiras com FinBERT (ProsusAI/finbert).
Retorna: positive | negative | neutral + score de confiança

Arquitetura:
    - Pipeline FinBERT carregado uma única vez na inicialização
    - Analisa lista de manchetes e retorna score agregado
    - Cache simples em memória para evitar reprocessamento
    - Integração com NewsAPI via get_news_sentiment()

Uso:
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze_news(news_list)
    print(result.signal)        # positive | negative | neutral
    print(result.score)         # 0.0 a 1.0
    print(result.news_count)    # qtd de notícias analisadas
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from newsapi import NewsApiClient

load_dotenv()
logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    """Resultado da análise de sentiment."""
    signal: str                    # positive | negative | neutral
    score: float                   # confiança média (0.0 – 1.0)
    news_count: int = 0            # qtd de notícias analisadas
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    headlines: list = field(default_factory=list)  # manchetes analisadas
    reason: str = ""


class SentimentAnalyzer:
    """
    Analisa sentiment de notícias financeiras usando FinBERT.

    Args:
        model_name:        Modelo HuggingFace (padrão: ProsusAI/finbert)
        min_confidence:    Score mínimo para considerar o sinal (padrão: 0.6)
        max_headlines:     Máximo de manchetes a analisar por chamada (padrão: 10)
        cache_ttl:         Tempo de vida do cache em segundos (padrão: 300)
    """

    def __init__(
        self,
        model_name: str = "ProsusAI/finbert",
        min_confidence: float = 0.6,
        max_headlines: int = 10,
        cache_ttl: int = 300,
    ):
        self.model_name = model_name
        self.min_confidence = min_confidence
        self.max_headlines = max_headlines
        self.cache_ttl = cache_ttl

        self._pipeline = None
        self._cache: dict[str, tuple[SentimentResult, float]] = {}  # key -> (result, timestamp)
        self._newsapi = NewsApiClient(api_key=os.getenv("NEWSAPI_KEY"))

    # ----------------------------------------------------------
    # INICIALIZAÇÃO DO MODELO
    # ----------------------------------------------------------

    def _load_model(self):
        """Carrega o pipeline FinBERT na primeira chamada (lazy loading)."""
        if self._pipeline is not None:
            return

        logger.info(f"Carregando modelo FinBERT: {self.model_name} (~440MB, pode demorar...)")
        try:
            from transformers import pipeline
            self._pipeline = pipeline(
                task="text-classification",
                model=self.model_name,
                tokenizer=self.model_name,
                device=-1,  # CPU
                truncation=True,
                max_length=512,
            )
            logger.info("FinBERT carregado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao carregar FinBERT: {e}")
            raise

    # ----------------------------------------------------------
    # MÉTODO PRINCIPAL
    # ----------------------------------------------------------

    def analyze_news(self, news_list: list[dict]) -> SentimentResult:
        """
        Analisa lista de notícias e retorna sentiment agregado.

        Args:
            news_list: Lista de dicts com chave 'title' e opcionalmente 'description'

        Returns:
            SentimentResult com signal, score e contagens
        """
        if not news_list:
            return SentimentResult(
                signal="neutral",
                score=0.0,
                news_count=0,
                reason="Nenhuma notícia disponível"
            )

        # Monta lista de textos
        texts = []
        for n in news_list[:self.max_headlines]:
            title = n.get("title", "").strip()
            desc  = n.get("description", "") or ""
            text  = f"{title}. {desc}".strip(". ") if desc else title
            if text:
                texts.append(text)

        if not texts:
            return SentimentResult(signal="neutral", score=0.0, reason="Textos vazios")

        # Verifica cache
        cache_key = "|".join(texts[:3])  # chave baseada nas 3 primeiras manchetes
        cached = self._get_cache(cache_key)
        if cached:
            logger.debug("Sentiment retornado do cache.")
            return cached

        # Carrega modelo se ainda não foi carregado
        self._load_model()

        # Classifica cada texto
        pos, neg, neu = 0, 0, 0
        pos_score, neg_score = [], []

        for text in texts:
            try:
                result = self._pipeline(text)[0]
                label = result["label"].lower()   # positive | negative | neutral
                score = result["score"]

                if label == "positive":
                    pos += 1
                    pos_score.append(score)
                elif label == "negative":
                    neg += 1
                    neg_score.append(score)
                else:
                    neu += 1
            except Exception as e:
                logger.warning(f"Erro ao classificar texto: {e}")
                neu += 1

        total = pos + neg + neu
        if total == 0:
            return SentimentResult(signal="neutral", score=0.0, reason="Nenhum texto classificado")

        # Sinal agregado por maioria
        if pos > neg and pos > neu:
            signal = "positive"
            avg_score = sum(pos_score) / len(pos_score) if pos_score else 0.5
            reason = f"{pos}/{total} notícias positivas (score médio: {avg_score:.2f})"
        elif neg > pos and neg > neu:
            signal = "negative"
            avg_score = sum(neg_score) / len(neg_score) if neg_score else 0.5
            reason = f"{neg}/{total} notícias negativas (score médio: {avg_score:.2f})"
        else:
            signal = "neutral"
            avg_score = 0.5
            reason = f"Empate ou maioria neutra (pos={pos}, neg={neg}, neu={neu})"

        # Aplica threshold de confiança
        if avg_score < self.min_confidence and signal != "neutral":
            reason += f" | Score abaixo do threshold ({avg_score:.2f} < {self.min_confidence}) → neutro"
            signal = "neutral"

        sr = SentimentResult(
            signal=signal,
            score=round(avg_score, 4),
            news_count=total,
            positive_count=pos,
            negative_count=neg,
            neutral_count=neu,
            headlines=[n.get("title", "") for n in news_list[:self.max_headlines]],
            reason=reason,
        )

        self._set_cache(cache_key, sr)
        return sr

    # ----------------------------------------------------------
    # NEWSAPI INTEGRADO
    # ----------------------------------------------------------

    def get_news_sentiment(self, keyword: str = "bitcoin", page_size: int = 10) -> SentimentResult:
        """
        Busca notícias na NewsAPI e retorna sentiment.
        Usa endpoint 'everything' para maior cobertura no plano free.

        Args:
            keyword:   Palavra-chave de busca (ex: 'bitcoin', 'ethereum')
            page_size: Quantidade de notícias a buscar (max: 100)

        Returns:
            SentimentResult com sentiment das notícias mais recentes
        """
        try:
            resp = self._newsapi.get_everything(
                q=keyword,
                language="en",
                sort_by="publishedAt",
                page_size=page_size,
            )

            if resp.get("status") != "ok":
                logger.warning(f"NewsAPI erro: {resp}")
                return SentimentResult(signal="neutral", score=0.0, reason="NewsAPI indisponível")

            articles = resp.get("articles", [])
            if not articles:
                return SentimentResult(signal="neutral", score=0.0, news_count=0, reason="Nenhuma notícia encontrada")

            news_list = [
                {
                    "title": a.get("title", ""),
                    "description": a.get("description", ""),
                    "source": a.get("source", {}).get("name", ""),
                    "url": a.get("url", ""),
                }
                for a in articles if a.get("title")
            ]

            logger.info(f"NewsAPI: {len(news_list)} notícias para '{keyword}'")
            return self.analyze_news(news_list)

        except Exception as e:
            logger.error(f"Erro ao buscar notícias: {e}")
            return SentimentResult(signal="neutral", score=0.0, reason=f"Erro: {e}")

    # ----------------------------------------------------------
    # CACHE
    # ----------------------------------------------------------

    def _get_cache(self, key: str) -> Optional[SentimentResult]:
        if key in self._cache:
            result, ts = self._cache[key]
            if time.time() - ts < self.cache_ttl:
                return result
            del self._cache[key]
        return None

    def _set_cache(self, key: str, result: SentimentResult):
        self._cache[key] = (result, time.time())


# ----------------------------------------------------------
# Teste rápido
# ----------------------------------------------------------
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    analyzer = SentimentAnalyzer(min_confidence=0.6)

    print("\n[1/2] Testando com notícias mockadas...")
    mock_news = [
        {"title": "Bitcoin surges to new all-time high as institutional demand grows"},
        {"title": "Crypto market rallies after Fed signals rate cuts"},
        {"title": "Ethereum upgrade boosts network performance significantly"},
        {"title": "Bitcoin faces regulatory uncertainty in major markets"},
        {"title": "Market analysts predict strong Q4 for cryptocurrency"},
    ]
    result = analyzer.analyze_news(mock_news)
    print(f"Sinal     : {result.signal}")
    print(f"Score     : {result.score}")
    print(f"Notícias  : {result.news_count} (pos={result.positive_count}, neg={result.negative_count}, neu={result.neutral_count})")
    print(f"Razão     : {result.reason}")

    print("\n[2/2] Testando com NewsAPI (bitcoin)...")
    result2 = analyzer.get_news_sentiment(keyword="bitcoin", page_size=5)
    print(f"Sinal     : {result2.signal}")
    print(f"Score     : {result2.score}")
    print(f"Notícias  : {result2.news_count}")
    print(f"Razão     : {result2.reason}")
    if result2.headlines:
        print("\nManchetes analisadas:")
        for h in result2.headlines:
            print(f"  - {h}")
