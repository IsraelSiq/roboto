"""
Roboto — Sentiment Analysis
Classifica notícias financeiras com FinBERT (ProsusAI/finbert).
Retorna: positive | negative | neutral + score de confiança

Arquitetura:
    - Pipeline FinBERT carregado uma única vez na inicialização (lazy loading)
    - Analisa lista de manchetes e retorna score agregado
    - Cache simples em memória para evitar reprocessamento
    - Fonte de notícias: cryptocurrency.cv (gratuito, sem API key)

Diagnóstico robusto (#5):
    - Loga o raw output do FinBERT antes de qualquer pós-processamento
    - Emite WARNING quando score == 0.50 exato (sinal de fallback estático)
    - Emite WARNING quando busca de notícias falha
    - Distingue fallback por erro de fallback intencional por falta de notícias
    - Campo `source` em SentimentResult indica de onde veio o resultado:
        'finbert' | 'cache' | 'fallback_no_news' | 'fallback_newsapi_error' |
        'fallback_finbert_error' | 'fallback_empty_texts'

Uso:
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze_news(news_list)
    print(result.signal)        # positive | negative | neutral
    print(result.score)         # 0.0 a 1.0
    print(result.news_count)    # qtd de notícias analisadas
    print(result.source)        # origem do resultado
    print(result.raw_scores)    # {'positive': 0.82, 'negative': 0.10, 'neutral': 0.08}
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Sentinel para detectar fallback estático
_FALLBACK_SCORE = 0.5
_FALLBACK_SCORE_TOLERANCE = 1e-9


def _is_suspicious_score(score: float) -> bool:
    """Retorna True se o score é exatamente 0.50 — sinal de fallback estático."""
    return abs(score - _FALLBACK_SCORE) < _FALLBACK_SCORE_TOLERANCE


@dataclass
class SentimentResult:
    """Resultado da análise de sentiment."""
    signal: str                # positive | negative | neutral
    score: float               # confiança média (0.0 – 1.0)
    news_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    headlines: list = field(default_factory=list)
    reason: str = ""

    # --- Campos novos para diagnóstico (#5 + #9) ---
    source: str = "finbert"
    # 'finbert' | 'cache' | 'fallback_no_news' |
    # 'fallback_newsapi_error' | 'fallback_finbert_error' |
    # 'fallback_empty_texts'
    raw_scores: dict = field(default_factory=dict)
    # ex: {'positive': 0.82, 'negative': 0.10, 'neutral': 0.08}
    # Vazio quando o FinBERT não chegou a rodar


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
        self._cache: dict[str, tuple[SentimentResult, float]] = {}

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
                device=-1,
                truncation=True,
                max_length=512,
                top_k=None,
            )
            logger.info("FinBERT carregado com sucesso.")
        except Exception as e:
            logger.error(f"[FinBERT] Falha ao carregar modelo '{self.model_name}': {e}")
            logger.error(
                "[FinBERT] O bot vai operar com sentiment=neutral "
                "enquanto o modelo não estiver disponível."
            )
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
            SentimentResult com signal, score, source e raw_scores
        """
        if not news_list:
            logger.debug("[Sentiment] Nenhuma notícia recebida → fallback neutral")
            return SentimentResult(
                signal="neutral",
                score=0.0,
                news_count=0,
                source="fallback_no_news",
                reason="Nenhuma notícia disponível"
            )

        texts = []
        for n in news_list[:self.max_headlines]:
            title = n.get("title", "").strip()
            desc = n.get("description", "") or ""
            text = f"{title}. {desc}".strip(". ") if desc else title
            if text:
                texts.append(text)

        if not texts:
            logger.warning(
                "[Sentiment] news_list recebida mas todos os textos estavam vazios → fallback neutral"
            )
            return SentimentResult(
                signal="neutral",
                score=0.0,
                source="fallback_empty_texts",
                reason="Textos vazios"
            )

        # Verifica cache
        cache_key = "|".join(texts[:3])
        cached = self._get_cache(cache_key)
        if cached:
            logger.debug("[Sentiment] Retornado do cache.")
            cached.source = "cache"
            return cached

        # Tenta carregar e rodar o FinBERT
        try:
            self._load_model()
        except Exception:
            logger.warning(
                "[Sentiment] FinBERT indisponível → fallback neutral (score=0.0). "
                "Verifique se os pesos do modelo estão baixados e o ambiente tem "
                "acesso à internet na primeira execução."
            )
            return SentimentResult(
                signal="neutral",
                score=0.0,
                news_count=len(texts),
                source="fallback_finbert_error",
                reason="FinBERT não pôde ser carregado"
            )

        # Classifica cada texto e coleta raw scores
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

                logger.debug(f"[FinBERT raw] {text[:60]!r} → {raw_dict}")

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
                logger.warning(f"[FinBERT] Erro ao classificar texto: {e} | texto: {text[:80]!r}")
                neu += 1

        total = pos + neg + neu
        if total == 0:
            return SentimentResult(
                signal="neutral",
                score=0.0,
                source="fallback_finbert_error",
                reason="Nenhum texto classificado com sucesso"
            )

        # Score médio por label
        avg_raw = {}
        if all_raw:
            for lbl in ("positive", "negative", "neutral"):
                values = [r.get(lbl, 0.0) for r in all_raw]
                avg_raw[lbl] = round(sum(values) / len(values), 4)

        logger.debug(
            f"[Sentiment] Agregado: pos={pos} neg={neg} neu={neu} | avg_raw={avg_raw}"
        )

        # Sinal por maioria
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

        # Threshold de confiança
        if avg_score < self.min_confidence and signal != "neutral":
            reason += f" | Score abaixo do threshold ({avg_score:.4f} < {self.min_confidence}) → neutro"
            signal = "neutral"

        # Alerta de fallback suspeito
        if _is_suspicious_score(avg_score) and signal != "neutral":
            logger.warning(
                f"[Sentiment] ATENÇÃO: score={avg_score} é exatamente 0.50 para sinal '{signal}'. "
                "Isso indica possível fallback estático. Verifique o FinBERT."
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
    logging.basicConfig(level=logging.DEBUG)

    analyzer = SentimentAnalyzer(min_confidence=0.6)

    print("\n[1/3] Testando com notícias mockadas positivas...")
    mock_pos = [
        {"title": "Bitcoin surges to new all-time high as institutional demand grows"},
        {"title": "Crypto market rallies after Fed signals rate cuts"},
        {"title": "Ethereum upgrade boosts network performance significantly"},
    ]
    r = analyzer.analyze_news(mock_pos)
    print(f"  Sinal    : {r.signal} | Score: {r.score} | Source: {r.source}")
    print(f"  Raw      : {r.raw_scores}")
    print(f"  Razão    : {r.reason}")

    print("\n[2/3] Testando com notícias mockadas negativas...")
    mock_neg = [
        {"title": "Bitcoin crashes 30%, panic selling sweeps the market"},
        {"title": "Regulatory crackdown sends crypto prices tumbling"},
        {"title": "Major exchange hacked, billions in losses reported"},
    ]
    r2 = analyzer.analyze_news(mock_neg)
    print(f"  Sinal    : {r2.signal} | Score: {r2.score} | Source: {r2.source}")
    print(f"  Raw      : {r2.raw_scores}")
    print(f"  Razão    : {r2.reason}")

    print("\n[3/3] Testando fallback (lista vazia)...")
    r3 = analyzer.analyze_news([])
    print(f"  Sinal    : {r3.signal} | Score: {r3.score} | Source: {r3.source}")
    print(f"  Razão    : {r3.reason}")
