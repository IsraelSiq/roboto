"""
Roboto — Sentiment Analysis
Classifica notícias financeiras com FinBERT (ProsusAI/finbert).
Retorna: positive | negative | neutral + score de confiança

Arquitetura:
    - Pipeline FinBERT carregado uma única vez na inicialização (lazy loading)
    - Analisa lista de manchetes e retorna score agregado
    - Cache simples em memória para evitar reprocessamento
    - Integração com NewsClient (CryptoPanic + RSS fallback) via get_news_sentiment()

Diagnóstico robusto (#5):
    - Loga o raw output do FinBERT antes de qualquer pós-processamento
    - Emite WARNING quando score == 0.50 exato (sinal de fallback estático)
    - Campo `source` em SentimentResult indica de onde veio o resultado:
        'finbert' | 'cache' | 'fallback_no_news' | 'fallback_newsapi_error' |
        'fallback_finbert_error' | 'fallback_empty_texts'

Uso:
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze_news(news_list)
    print(result.signal)      # positive | negative | neutral
    print(result.score)       # 0.0 a 1.0
    print(result.source)      # origem do resultado
    print(result.raw_scores)  # {'positive': 0.82, 'negative': 0.10, 'neutral': 0.08}
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_FALLBACK_SCORE = 0.5
_FALLBACK_SCORE_TOLERANCE = 1e-9


def _is_suspicious_score(score: float) -> bool:
    """Retorna True se o score é exatamente 0.50 — sinal de fallback estático."""
    return abs(score - _FALLBACK_SCORE) < _FALLBACK_SCORE_TOLERANCE


@dataclass
class SentimentResult:
    """Resultado da análise de sentiment."""
    signal: str
    score: float
    news_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    headlines: list = field(default_factory=list)
    reason: str = ""
    source: str = "finbert"
    raw_scores: dict = field(default_factory=dict)


class SentimentAnalyzer:
    """
    Analisa sentiment de notícias financeiras usando FinBERT.

    Args:
        model_name:     Modelo HuggingFace (padrão: ProsusAI/finbert)
        min_confidence: Score mínimo para considerar o sinal (padrão: 0.6)
        max_headlines:  Máximo de manchetes a analisar por chamada (padrão: 10)
        cache_ttl:      Tempo de vida do cache em segundos (padrão: 300)
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
        self._cache: dict[str, tuple[SentimentResult, float]] = {}

        # NewsClient lazy (instanciado na primeira chamada)
        self._news_client = None

    def _get_news_client(self):
        """Retorna o NewsClient, instanciando na primeira chamada."""
        if self._news_client is None:
            from backend.market.news_client import NewsClient
            self._news_client = NewsClient()
        return self._news_client

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
                device=-1,
                truncation=True,
                max_length=512,
                top_k=None,
            )
            logger.info("FinBERT carregado com sucesso.")
        except Exception as e:
            logger.error(f"[FinBERT] Falha ao carregar modelo '{self.model_name}': {e}")
            raise

    def analyze_news(self, news_list: list[dict]) -> SentimentResult:
        """Analisa lista de notícias e retorna sentiment agregado."""
        if not news_list:
            return SentimentResult(
                signal="neutral", score=0.0, news_count=0,
                source="fallback_no_news", reason="Nenhuma notícia disponível"
            )

        texts = []
        for n in news_list[:self.max_headlines]:
            title = n.get("title", "").strip()
            desc = n.get("description", "") or ""
            text = f"{title}. {desc}".strip(". ") if desc else title
            if text:
                texts.append(text)

        if not texts:
            return SentimentResult(
                signal="neutral", score=0.0,
                source="fallback_empty_texts", reason="Textos vazios"
            )

        cache_key = "|".join(texts[:3])
        cached = self._get_cache(cache_key)
        if cached:
            cached.source = "cache"
            return cached

        try:
            self._load_model()
        except Exception:
            return SentimentResult(
                signal="neutral", score=0.0, news_count=len(texts),
                source="fallback_finbert_error", reason="FinBERT não pôde ser carregado"
            )

        pos, neg, neu = 0, 0, 0
        pos_scores, neg_scores = [], []
        all_raw: list[dict] = []

        for text in texts:
            try:
                raw_output = self._pipeline(text)
                if raw_output and isinstance(raw_output[0], list):
                    raw_output = raw_output[0]
                raw_dict = {r["label"].lower(): round(r["score"], 4) for r in raw_output}
                all_raw.append(raw_dict)
                best = max(raw_output, key=lambda x: x["score"])
                label = best["label"].lower()
                score = best["score"]
                if label == "positive":
                    pos += 1
                    pos_scores.append(score)
                elif label == "negative":
                    neg += 1
                    neg_scores.append(score)
                else:
                    neu += 1
            except Exception as e:
                logger.warning(f"[FinBERT] Erro ao classificar texto: {e}")
                neu += 1

        total = pos + neg + neu
        if total == 0:
            return SentimentResult(
                signal="neutral", score=0.0,
                source="fallback_finbert_error", reason="Nenhum texto classificado"
            )

        avg_raw = {}
        if all_raw:
            for lbl in ("positive", "negative", "neutral"):
                values = [r.get(lbl, 0.0) for r in all_raw]
                avg_raw[lbl] = round(sum(values) / len(values), 4)

        if pos > neg and pos > neu:
            signal = "positive"
            avg_score = sum(pos_scores) / len(pos_scores) if pos_scores else 0.5
            reason = f"{pos}/{total} notícias positivas (score médio: {avg_score:.4f})"
        elif neg > pos and neg > neu:
            signal = "negative"
            avg_score = sum(neg_scores) / len(neg_scores) if neg_scores else 0.5
            reason = f"{neg}/{total} notícias negativas (score médio: {avg_score:.4f})"
        else:
            signal = "neutral"
            avg_score = avg_raw.get("neutral", 0.5)
            reason = f"Empate ou maioria neutra (pos={pos}, neg={neg}, neu={neu})"

        if avg_score < self.min_confidence and signal != "neutral":
            reason += f" | Score abaixo do threshold ({avg_score:.4f} < {self.min_confidence})"
            signal = "neutral"

        if _is_suspicious_score(avg_score):
            logger.warning(
                f"[FinBERT] Score suspeito de fallback estático detectado: {avg_score:.6f}"
            )

        sr = SentimentResult(
            signal=signal,
            score=round(avg_score, 4),
            news_count=total,
            positive_count=pos,
            negative_count=neg,
            neutral_count=neu,
            headlines=[n.get("title", "") for n in news_list[:self.max_headlines]],
            reason=reason,
            source="finbert",
            raw_scores=avg_raw,
        )
        self._set_cache(cache_key, sr)
        return sr

    def get_news_sentiment(
        self,
        keyword: str = "bitcoin",
        news_limit: int = 10,
        # alias de compatibilidade (era page_size na NewsAPI)
        page_size: Optional[int] = None,
    ) -> SentimentResult:
        """
        Busca notícias via NewsClient (CryptoPanic + RSS fallback)
        e retorna o sentiment classificado pelo FinBERT.

        Args:
            keyword:    Palavra-chave (ex: 'bitcoin', 'bnb')
            news_limit: Máximo de notícias a buscar (padrão: 10)
            page_size:  Alias legado de news_limit (ignorado se news_limit for fornecido)
        """
        limit = news_limit if page_size is None else page_size
        try:
            client = self._get_news_client()
            news_list = client.get_news(keyword=keyword, limit=limit)

            if not news_list:
                logger.warning(
                    f"[Sentiment] NewsClient não retornou notícias para '{keyword}' "
                    "(CryptoPanic e RSS indisponíveis ou sem resultados)"
                )
                return SentimentResult(
                    signal="neutral", score=0.0, news_count=0,
                    source="fallback_no_news",
                    reason="Nenhuma notícia disponível (NewsClient vazio)"
                )

            logger.info(
                f"[Sentiment] {len(news_list)} notícias obtidas para '{keyword}' "
                f"via NewsClient"
            )
            return self.analyze_news(news_list)

        except Exception as e:
            logger.warning(
                f"[Sentiment] Erro no NewsClient para '{keyword}': {e} — usando neutral"
            )
            return SentimentResult(
                signal="neutral", score=0.0,
                source="fallback_newsapi_error",
                reason=f"Exceção no NewsClient: {e}"
            )

    def _get_cache(self, key: str) -> Optional[SentimentResult]:
        if key in self._cache:
            result, ts = self._cache[key]
            if time.time() - ts < self.cache_ttl:
                return result
            del self._cache[key]
        return None

    def _set_cache(self, key: str, result: SentimentResult):
        self._cache[key] = (result, time.time())
