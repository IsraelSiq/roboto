"""
conftest.py — fixtures globais de teste.

O CI nao tem acesso a internet para baixar o FinBERT (~440MB) nem credenciais
reais de NewsAPI/Binance. Este conftest mocka automaticamente os pontos de I/O
externo para que os testes unitarios rodem 100% offline.

Nota (#48): mock_finbert_pipeline NAO usa autouse=True pois testes de sentiment
precisam controlar o retorno do pipeline individualmente (positive/negative/neutral).
Aplique o fixture explicitamente apenas nos testes que nao controlam o pipeline.

Nota (#50): mock_binance_env injeta variaveis de ambiente falsas para todos os testes,
evitando ValueError de BinanceClient.__init__() em clone limpo ou CI sem .env.
"""

import os
import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def mock_binance_env(monkeypatch):
    """Injeta BINANCE_API_KEY e BINANCE_SECRET falsos para todos os testes.

    Evita ValueError em BinanceClient.__init__() quando .env nao existe
    (clone limpo, CI, GitHub Actions, etc.).
    Nao afeta testes de integracao que usam credenciais reais via .env.
    """
    monkeypatch.setenv("BINANCE_API_KEY", "fake_key_for_tests")
    monkeypatch.setenv("BINANCE_SECRET", "fake_secret_for_tests")


@pytest.fixture(autouse=True)
def mock_news_client(monkeypatch):
    """Evita chamadas reais a NewsClient em todos os testes."""
    mock_client = MagicMock()
    mock_client.get_news.return_value = [
        {"title": "Bitcoin rallies", "description": "BTC up 5%"},
        {"title": "Crypto market grows", "description": "Altcoins follow"},
    ]
    monkeypatch.setattr(
        "backend.market.news_client.NewsClient",
        lambda: mock_client,
    )
    return mock_client


@pytest.fixture
def mock_finbert_pipeline(monkeypatch):
    """Mocka o pipeline FinBERT com retorno fixo 'positive'.

    Use este fixture explicitamente em testes que nao precisam controlar
    o resultado do FinBERT. Testes de sentiment que precisam simular
    'negative' ou 'neutral' devem usar patch.object(analyzer, '_pipeline')
    diretamente, sem este fixture.
    """
    mock_pipe = MagicMock()
    mock_pipe.return_value = [
        [{"label": "positive", "score": 0.82},
         {"label": "negative", "score": 0.10},
         {"label": "neutral",  "score": 0.08}]
    ]
    monkeypatch.setattr(
        "backend.analysis.sentiment._FINBERT_PIPELINE",
        mock_pipe,
    )
    return mock_pipe
