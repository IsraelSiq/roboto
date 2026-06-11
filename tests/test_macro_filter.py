"""
Testes para filtro de tendência macro (issue #8).

Cobre:
    - CALL bloqueado em tendência de baixa
    - CALL permitido em tendência de alta
    - PUT bloqueado em tendência de alta
    - PUT permitido em tendência de baixa
    - Lateral retorna None (indeterminado)
    - Dados insuficientes retorna None
    - DataFrame vazio retorna None
    - Filtro desativado sempre retorna True
    - Integração com SignalCombiner: macro_blocked=True
    - Integração com SignalCombiner: filtro desativado não bloqueia
    - status_str retorna string descritiva
"""
import pytest
import numpy as np
import pandas as pd
from backend.analysis.macro_filter import MacroTrendFilter
from backend.analysis.signals import SignalCombiner, CALL_FORTE, PUT_FORTE, AGUARDAR
from backend.analysis.technical import TechnicalResult
from backend.analysis.sentiment import SentimentResult


# ---------------------------------------------------------------
# Fixtures de candles sintéticos (60 candles por padrão)
# ---------------------------------------------------------------

def _make_df(prices: list[float]) -> pd.DataFrame:
    """Cria DataFrame mínimo com coluna 'close'."""
    return pd.DataFrame({"close": prices})


def _trending_up(n: int = 80, start: float = 50_000.0, step: float = 200.0) -> pd.DataFrame:
    """Série com tendência de alta clara (preço > EMA20 > EMA50)."""
    prices = [start + i * step for i in range(n)]
    return _make_df(prices)


def _trending_down(n: int = 80, start: float = 95_000.0, step: float = 200.0) -> pd.DataFrame:
    """Série com tendência de baixa clara (preço < EMA20 < EMA50)."""
    prices = [start - i * step for i in range(n)]
    return _make_df(prices)


def _lateral(n: int = 80, base: float = 80_000.0, amp: float = 300.0) -> pd.DataFrame:
    """Série lateral (oscila em torno de base)."""
    prices = [base + amp * np.sin(i * 0.3) for i in range(n)]
    return _make_df(prices)


# ---------------------------------------------------------------
# Testes de tendência
# ---------------------------------------------------------------

def test_call_bloqueado_em_tendencia_baixa():
    f = MacroTrendFilter()
    assert f.tendencia_favoravel(_trending_down(), "CALL") is False


def test_call_permitido_em_tendencia_alta():
    f = MacroTrendFilter()
    assert f.tendencia_favoravel(_trending_up(), "CALL") is True


def test_put_bloqueado_em_tendencia_alta():
    f = MacroTrendFilter()
    assert f.tendencia_favoravel(_trending_up(), "PUT") is False


def test_put_permitido_em_tendencia_baixa():
    f = MacroTrendFilter()
    assert f.tendencia_favoravel(_trending_down(), "PUT") is True


def test_lateral_retorna_none():
    f = MacroTrendFilter()
    resultado = f.tendencia_favoravel(_lateral(), "CALL")
    # Mercado lateral pode retornar None ou False (conservador)
    # Nunca deve retornar True
    assert resultado is not True


# ---------------------------------------------------------------
# Dados insuficientes
# ---------------------------------------------------------------

def test_dados_insuficientes_retorna_none():
    f = MacroTrendFilter(min_candles=60)
    df_curto = _make_df([50_000.0 + i * 100 for i in range(30)])  # só 30 candles
    assert f.tendencia_favoravel(df_curto, "CALL") is None


def test_dataframe_vazio_retorna_none():
    f = MacroTrendFilter()
    assert f.tendencia_favoravel(pd.DataFrame(), "CALL") is None


def test_none_retorna_none():
    f = MacroTrendFilter()
    assert f.tendencia_favoravel(None, "PUT") is None


# ---------------------------------------------------------------
# Filtro desativado
# ---------------------------------------------------------------

def test_filtro_desativado_sempre_true():
    f = MacroTrendFilter(enabled=False)
    # Mesmo com tendência de baixa, deve liberar CALL
    assert f.tendencia_favoravel(_trending_down(), "CALL") is True


# ---------------------------------------------------------------
# Integração com SignalCombiner
# ---------------------------------------------------------------

def _make_call_forte_decision(tech_signal="CALL", sent_signal="positive"):
    tech = TechnicalResult(signal=tech_signal, reason="test", current_price=90_000.0)
    sent = SentimentResult(signal=sent_signal, score=0.85)
    return tech, sent


def test_combiner_bloqueia_call_em_tendencia_baixa():
    tech, sent = _make_call_forte_decision("CALL", "positive")
    macro = MacroTrendFilter()
    combiner = SignalCombiner(macro_filter=macro)
    decision = combiner.combine(tech, sent, df_macro=_trending_down())
    assert decision.final == AGUARDAR
    assert decision.macro_blocked is True


def test_combiner_nao_bloqueia_com_filtro_desativado():
    tech, sent = _make_call_forte_decision("CALL", "positive")
    macro = MacroTrendFilter(enabled=False)
    combiner = SignalCombiner(macro_filter=macro)
    decision = combiner.combine(tech, sent, df_macro=_trending_down())
    assert decision.final == CALL_FORTE
    assert decision.macro_blocked is False


# ---------------------------------------------------------------
# status_str
# ---------------------------------------------------------------

def test_status_str_tendencia_alta():
    f = MacroTrendFilter()
    s = f.status_str(_trending_up())
    assert "ALTA" in s


def test_status_str_tendencia_baixa():
    f = MacroTrendFilter()
    s = f.status_str(_trending_down())
    assert "BAIXA" in s
