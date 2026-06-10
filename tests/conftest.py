"""
conftest.py — fixtures globais de teste.

O CI nao tem acesso a internet para baixar o FinBERT (~440MB) nem credenciais
reais de NewsAPI/Binance. Este conftest mocka automaticamente os pontos de I/O
externo para que os testes unitarios rodem 100% offline.
"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def mock_newsapi(monkeypatch):
    """Evita chamadas reais à NewsAPI em todos os testes."""
    mock_client = MagicMock()
    mock_client.get_everything.return_value = {
        "status": "ok",
        "articles": [
            {"title": "Bitcoin rallies", "description": "BTC up 5%"},
            {"title": "Crypto market grows", "description": "Altcoins follow"},
        ],
    }
    monkeypatch.setattr(
        "backend.analysis.sentiment.NewsApiClient",
        lambda **kwargs: mock_client,
    )
    return mock_client


@pytest.fixture(autouse=True)
def mock_finbert_pipeline(monkeypatch):
    """Evita download e carregamento do FinBERT (~440MB) em todos os testes."""
    mock_pipe = MagicMock()
    mock_pipe.return_value = [
        [{"label": "positive", "score": 0.82},
         {"label": "negative", "score": 0.10},
         {"label": "neutral",  "score": 0.08}]
    ]
    monkeypatch.setattr(
        "backend.analysis.sentiment.SentimentAnalyzer._load_model",
        lambda self: setattr(self, "_pipeline", mock_pipe),
    )
    return mock_pipe
