"""
Roboto — Sentiment Analysis
Classifica notícias financeiras com FinBERT (ProsusAI/finbert).
Retorna: positive | negative | neutral + score de confiança

Arquitetura:
    - Pipeline FinBERT lazy: carregado na primeira análise real, não no __init__
    - threading.Lock garante que só uma thread carrega o modelo (safe para ASGI)
    - Singleton global _FINBERT_PIPELINE: compartilhado entre instâncias (#14)
    - Cache em memória por instância (TTL configurável, padrão: 300s)
    - Cache Supabase: consulta news_cache antes de chamar NewsClient+FinBERT (#15)
    - Integração com NewsClient (cryptocurrency.cv + RSS fallback)
    - Expõe self.last_news com a lista bruta de notícias (#52)

Hieraráquia de cache em get_news_sentiment() (#15):
    1. Cache memória (in-process, TTL=300s por padrão)
    2. Cache Supabase news_cache (TTL=NEWS_CACHE_TTL_MINUTES, padrão 15min)
    3. NewsClient + FinBERT (fonte primária, resultado persiste no Supabase)

Diagnóstico robusto (#5):
    - Loga o raw output do FinBERT antes de qualquer pós-processamento
    - Emite WARNING quando score == 0.50 exato (sinal de fallback estático)
    - Campo `source` em SentimentResult indica de onde veio o resultado:
        'finbert' | 'cache' | 'supabase_cache' |
        'fallback_no_news' | 'fallback_newsapi_error' |
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

    # Acesso às notícias brutas após chamada (para NewsImpactCollector #52):
    print(analyzer.last_news)  # lista de dicts com title, published_at, source
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_FALLBACK_SCORE = 0.5
_FALLBACK_SCORE_TOLERANCE = 1e-9

# TTL do cache Supabase (minutos) — configurado via .env (#15)
_NEWS_CACHE_TTL_MINUTES: int = int(os.getenv("NEWS_CACHE_TTL_MINUTES", "15"))

# -------------------------------------------------------------------
# Singleton global thread-safe para o pipeline FinBERT (#14)
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
        cache_ttl:      Tempo de vida do cache em memória em segundos (padrão: 300)

    Atributos públicos:
        last_news (list[dict]): Lista bruta de notícias da última chamada a
            get_news_sentiment() via NewsClient (path principal, não cache).
            Cada dict contém title, description, published_at, source.
            Vazia se o resultado veio do cache Supabase ou memória.
            Usada pelo NewsImpactCollector (#52) para persistir cada notícia.
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
        self._db = None  # SupabaseClient lazy (#15)

        # Lista bruta de notícias da última chamada via NewsClient (#52)
        # Atualizada apenas quando o path real (NewsClient+FinBERT) é executado
        self.last_news: list[dict] = []

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
    # Lazy clients
    # ----------------------------------------------------------

    def _get_news_client(self):
        if self._news_client is None:
            from backend.market.news_client import NewsClient
            self._news_client = NewsClient()
        return self._news_client

    def _get_db(self):
        """Retorna SupabaseClient lazy. Retorna None se Supabase não estiver configurado."""
        if self._db is None:
            try:
                from backend.db.supabase_client import SupabaseClient
                self._db = SupabaseClient()
            except Exception as e:
                logger.warning(f"[NewsCache] Supabase indisponível — cache desativado: {e}")
                self._db = False  # marca como indisponível para não tentar novamente
        return self._db if self._db is not False else None

    # ----------------------------------------------------------
    # Lazy loading thread-safe (#14)
    # ----------------------------------------------------------

    def _load_model(self):
        """
        Carrega o pipeline FinBERT na primeira chamada (lazy loading).
        Thread-safe via double-checked locking.
        """
        global _FINBERT_PIPELINE

        if _FINBERT_PIPELINE is not None:
            return

        with _FINBERT_LOCK:
            if _FINBERT_PIPELINE is not None:
                return

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
        symbol: Optional[str] = None,
    ) -> SentimentResult:
        """
        Busca notícias e retorna o sentiment classificado pelo FinBERT.

        Hierarquia de cache (#15):
            1. Cache Supabase (TTL=NEWS_CACHE_TTL_MINUTES) — evita NewsClient+FinBERT
            2. NewsClient (cryptocurrency.cv + RSS fallback) + FinBERT
            3. Persiste resultado novo em news_cache para próximos ciclos

        Graceful degradation: se Supabase offline, flui direto para NewsClient.

        Atualiza self.last_news com a lista bruta (path NewsClient) para uso
        pelo NewsImpactCollector (#52). Permanece [] se veio do cache.

        Args:
            keyword:    Palavra-chave de busca (ex: 'bitcoin', 'bnb')
            news_limit: Máximo de notícias (padrão: 10)
            page_size:  Alias legado de news_limit
            symbol:     Símbolo para cache Supabase (ex: 'BTCUSDT'). Se None, usa keyword.
        """
        limit = news_limit if page_size is None else page_size
        cache_symbol = symbol or keyword.upper()

        # Limpa last_news antes de cada chamada
        self.last_news = []

        # --- 1. Tenta cache Supabase (#15) ---
        db = self._get_db()
        if db is not None:
            try:
                cached_rows = db.get_cached_news(
                    symbol=cache_symbol,
                    ttl_minutes=_NEWS_CACHE_TTL_MINUTES,
                    limit=limit,
                )
                if cached_rows:
                    # Reconstrói SentimentResult a partir dos scores já calculados
                    sentiments = [r.get("sentiment", "neutral") for r in cached_rows]
                    scores = [float(r.get("score") or 0.5) for r in cached_rows]
                    headlines = [r.get("title", "") for r in cached_rows]

                    pos = sentiments.count("positive")
                    neg = sentiments.count("negative")
                    neu = sentiments.count("neutral")
                    total = len(sentiments)

                    if pos > neg and pos > neu:
                        signal = "positive"
                        avg_score = sum(s for s, lbl in zip(scores, sentiments) if lbl == "positive") / max(pos, 1)
                        reason = f"{pos}/{total} positivas [supabase_cache TTL={_NEWS_CACHE_TTL_MINUTES}min]"
                    elif neg > pos and neg > neu:
                        signal = "negative"
                        avg_score = sum(s for s, lbl in zip(scores, sentiments) if lbl == "negative") / max(neg, 1)
                        reason = f"{neg}/{total} negativas [supabase_cache TTL={_NEWS_CACHE_TTL_MINUTES}min]"
                    else:
                        signal = "neutral"
                        avg_score = sum(scores) / total if total else 0.5
                        reason = f"Neutra/empate [supabase_cache TTL={_NEWS_CACHE_TTL_MINUTES}min]"

                    logger.info(
                        f"[NewsCache] Hit Supabase para '{cache_symbol}': "
                        f"{total} notícias → {signal} ({avg_score:.4f})"
                    )
                    # last_news permanece [] — dados já persistidos no ciclo anterior
                    return SentimentResult(
                        signal=signal,
                        score=round(avg_score, 4),
                        news_count=total,
                        positive_count=pos,
                        negative_count=neg,
                        neutral_count=neu,
                        headlines=headlines,
                        reason=reason,
                        source="supabase_cache",
                    )
            except Exception as e:
                logger.warning(f"[NewsCache] Falha ao ler cache Supabase: {e} — seguindo para NewsClient")

        # --- 2. NewsClient + FinBERT ---
        try:
            client = self._get_news_client()
            news_list = client.get_news(keyword=keyword, limit=limit)

            # Expoe para o NewsImpactCollector (#52)
            self.last_news = news_list

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
            result = self.analyze_news(news_list)

            # --- 3. Persiste no Supabase para próximos ciclos (#15) ---
            if db is not None and result.source == "finbert":
                try:
                    articles_to_cache = [
                        {
                            "title":       n.get("title", ""),
                            "description": n.get("description"),
                            "source":      n.get("source"),
                            "url":         n.get("url"),
                            "sentiment":   result.signal,
                            "score":       result.score,
                        }
                        for n in news_list[:self.max_headlines]
                    ]
                    db.cache_news(symbol=cache_symbol, articles=articles_to_cache)
                    logger.debug(
                        f"[NewsCache] {len(articles_to_cache)} notícias persistidas "
                        f"em news_cache para '{cache_symbol}'"
                    )
                except Exception as e:
                    logger.warning(f"[NewsCache] Falha ao persistir cache: {e}")

            return result

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
