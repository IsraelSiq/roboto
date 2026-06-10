"""
Roboto — Núcleo de Sinais ✉
Combina sinal técnico (RSI+MACD+EMA+BB) com sentiment (FinBERT)
e gera a decisão final de trading.

Tabela de decisão:
    Técnico   | Sentiment | Decisão
    ----------|-----------|------------------
    CALL      | positive  | CALL_FORTE
    CALL      | neutral   | CALL_FRACO
    CALL      | negative  | AGUARDAR
    PUT       | negative  | PUT_FORTE
    PUT       | neutral   | PUT_FRACO
    PUT       | positive  | AGUARDAR
    AGUARDAR  | qualquer  | AGUARDAR

Log detalhado (#9):
    - Nível DEBUG exibe breakdown completo por componente
    - Nível INFO mantém formato original (compatível com parsers existentes)
    - SignalDecision agora expõe:
        sentiment_raw       → raw scores do FinBERT {positive, negative, neutral}
        sentiment_source    → origem do sentiment ('finbert'|'cache'|'fallback_*')
        sentiment_reason    → motivo detalhado do sentiment
    - WARNING emitido quando sentiment_source começa com 'fallback'
    - WARNING emitido quando sentiment_score é suspeito (== 0.50 exato)

Uso:
    from backend.analysis.signals import SignalCombiner
    combiner = SignalCombiner()
    decision = combiner.combine(technical_result, sentiment_result)
    print(decision.final)           # CALL_FORTE | PUT_FORTE | CALL_FRACO | PUT_FRACO | AGUARDAR
    print(decision.sentiment_raw)   # {'positive': 0.82, 'negative': 0.10, 'neutral': 0.08}
    print(decision.sentiment_source)  # 'finbert' | 'fallback_newsapi_error' | ...
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

from backend.analysis.technical import TechnicalResult
from backend.analysis.sentiment import SentimentResult, _is_suspicious_score

load_dotenv()
logger = logging.getLogger(__name__)

# Decis