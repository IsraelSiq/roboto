"""
Roboto — Sentiment Analysis
Classifica notícias financeiras com FinBERT (ProsusAI/finbert).
Retorna: positive | negative | neutral + score de confiança

Arquitetura:
    - Pipeline FinBERT lazy: carregado na primeira análise real, não no __init__
    - threading.Lock garante que só uma thread carrega o modelo (safe para ASGI)
    - Singleton global _FINBERT_PIPELINE: compartilhado entre instâncias (#14)
    - Cache em memória por instância (TTL configurável, padrão: 300s)
    - Integração com NewsClient (CryptoPanic + RSS fallback)

Diagnóstico robusto (#5):
    - Loga o raw output do FinBERT antes de qualquer pós-processamento
    - Emite WARNING quando score == 0.50 exato (sinal de fallback estático)
    - Campo `source` em SentimentResult indica de onde veio o resultado:
        'finbert' | 'cache' | 'fallback_no_news' | 'fallback_newsapi_error' |
        'fallback_finbert_error' | 'fallback_empty_texts'

Pré-aquecimento (#14):
    - warmup() carrega o modelo explicitamente (para deploy / cold start)
    - is_model_loaded: True após primeira carga bem-sucedida
    - Endpoint GET /warmup na API aciona warmup em background thread

Uso:
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze_news(news_list)
    print(result.signal)      # positive | negative | neutral
    print(result.score)       # 0.0 a 1.0
    print(result.source)      # origem do resultado
    print(result.raw_scores)  # {'positive': 0.82, 'negative': 0.10, 'neutral': 0.08}
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_FALLBACK_SCORE = 0.5
_FALLBACK_SCORE_TOLERANCE = 1e-9

# -------------------------------------------------------------------
# Singleton global thread-safe para o pipeline FinBERT (#14)
# Compartilhado entre todas as instâncias de SentimentAnalyzer para
# evitar carregar o modelo (~440 MB) mais de uma vez por processo.
# -------------------------------------------------------------------
_FINBERT_PIPELINE = None
_FINBERT_LOCK = threading.Lock()


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
        self._cache: dict[str, tuple[SentimentResult, float]] = {}
        self._news_client = None

    # ----------------------------------------------------------
    # Propriedades públicas (#14)
    # ----------------------------------------------------------

    @property
    def is_model_loaded(self) -> bool:
        """True se o pipeline FinBERT já foi carregado neste processo."""
        return _FINBERT_PIPELINE is not None

    def warmup(self) -> bool:
        """
        Pré-aquece o modelo FinBERT explicitamente.
        Útil para deploy — evita timeout na primeira requisição real.

        Returns:
            True se o modelo foi carregado com sucesso, False se houve erro.
        """
        if self.is_model_loaded:
            logger.info("[FinBERT] Modelo já carregado. Warmup ignorado.")
            return True
        try:
            self._load_model()
            return True
        except Exception as e:
            logger.error(f"[FinBERT] Warmup falhou: {e}")
            return False

    # ----------------------------------------------------------
    # NewsClient lazy
    # ----------------------------------------------------------

    def _get_news_client(self):
        if self._news_client is None:
            from backend.market.news_client import NewsClient
            self._news_client = NewsClient()
        return self._news_client

    # ----------------------------------------------------------
    # Lazy loading thread-safe (#14)
    # ----------------------------------------------------------

    def _load_model(self):
        """
        Carrega o pipeline FinBERT na primeira chamada (lazy loading).

        Thread-safe via double-checked locking:
        - Verifica sem trava (fast path)
        - Adquire _FINBERT_LOCK
        - Verifica novamente dentro da trava (evita double-load)
        """
        global _FINBERT_PIPELINE

        if _FINBERT_PIPELINE is not None:
            return  # fast path

        with _FINBERT_LOCK:
            if _FINBERT_PIPELINE is not None:
                return  # outra thread carregou enquanto esperávamos

            logger.info(
                f"[FinBERT] Carregando modelo: {self.model_name} "
                "(~440 MB, pode demorar na primeira vez...)"
            )
            t0 = time.time()
            try:
                from transformers import pipeline
                _FINBERT_PIPELINE = pipeline(
                    task="text-classification",
                    model=self.model_name,
                    tokenizer=self.model_name,
                    device=-1,
                    truncation=True,
                    max_length=512,
                    top_k=None,
                )
                elapsed = time.time() - t0
                logger.info(f"[FinBERT] Modelo carregado em {elapsed:.1f}s ✅")
            except Exception as e:
                logger.error(f"[FinBERT] Falha ao carregar modelo '{self.model_name}': {e}")
                raise

    # ----------------------------------------------------------
    # Análise principal
    # ----------------------------------------------------------

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
                raw_output = _FINBERT_PIPELINE(text)
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
        page_size: Optional[int] = None,
    ) -> SentimentResult:
        """
        Busca notícias via NewsClient (CryptoPanic + RSS fallback)
        e retorna o sentiment classificado pelo FinBERT.
        """
        limit = news_limit if page_size is None else page_size
        try:
            client = self._get_news_client()
            news_list = client.get_news(keyword=keyword, limit=limit)

            if not news_list:
                logger.warning(
                    f"[Sentiment] NewsClient não retornou notícias para '{keyword}'"
                )
                return SentimentResult(
                    signal="neutral", score=0.0, news_count=0,
                    source="fallback_no_news",
                    reason="Nenhuma notícia disponível (NewsClient vazio)"
                )

            logger.info(f"[Sentiment] {len(news_list)} notícias obtidas para '{keyword}'")
            return self.analyze_news(news_list)

        except Exception as e:
            logger.warning(f"[Sentiment] Erro no NewsClient para '{keyword}': {e} — usando neutral")
            return SentimentResult(
                signal="neutral", score=0.0,
                source="fallback_newsapi_error",
                reason=f"Exceção no NewsClient: {e}"
            )

    # ----------------------------------------------------------
    # Cache interno (por instância)
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
