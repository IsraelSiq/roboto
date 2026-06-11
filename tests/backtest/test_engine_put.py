"""
tests/backtest/test_engine_put.py
Valida explicitamente o suporte a PUT no BacktestEngine (issue #6).

Estratégia dos testes:
- Mocka o TechnicalAnalyzer para devolver PUT de forma determinística.
- Usa sentiment_mode='negative' para forçar PUT_FORTE.
- Garante que o trade aberto no backtest tem direction='PUT'.
- Garante que SL/TP ficam invertidos corretamente para short.
"""

from unittest.mock import patch
import pandas as pd

from backend.backtest.engine import BacktestEngine, MIN_CANDLES
from backend.analysis.technical import TechnicalResult


def _make_df(length=80, start_price=100.0):
    rows = []
    price = start_price
    for i in range(length):
        rows.append({
            "open_time": pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=5 * i),
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price,
            "volume": 1_000,
        })
        price -= 0.5
    return pd.DataFrame(rows)


def test_backtest_engine_aceita_sentiment_negative():
    engine = BacktestEngine(sentiment_mode="negative")
    assert engine._sentiment.signal == "negative"
    assert engine._sentiment.source == "backtest_mock"
    assert engine._sentiment.raw_scores["negative"] > engine._sentiment.raw_scores["positive"]


def test_backtest_engine_rejeita_sentiment_invalido():
    try:
        BacktestEngine(sentiment_mode="bearish")
        assert False, "Era esperado ValueError para sentiment_mode inválido"
    except ValueError as e:
        assert "sentiment_mode inválido" in str(e)


def test_backtest_abre_trade_put_quando_tecnico_put_e_sentiment_negative():
    df = _make_df()
    engine = BacktestEngine(
        symbol="BTCUSDT",
        interval="5m",
        only_strong=True,
        sentiment_mode="negative",
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
        max_trades_day=20,
    )

    tech_put = TechnicalResult(
        signal="PUT",
        reason="mock-put",
        rsi=80.0,
        macd=-5.0,
        macd_signal=-3.0,
        ema50=105.0,
        bb_upper=102.0,
        bb_lower=95.0,
        current_price=100.0,
    )

    with patch.object(engine.ta, "analyze", return_value=tech_put):
        result = engine.run(df)

    assert result.total_trades >= 1
    first_trade = result.trades[0]
    assert first_trade.direction == "PUT"
    assert first_trade.stop_loss > first_trade.entry_price
    assert first_trade.take_profit < first_trade.entry_price


def test_backtest_put_fecha_com_lucro_quando_preco_cai():
    df = _make_df(length=90, start_price=100.0)
    engine = BacktestEngine(
        symbol="BTCUSDT",
        interval="5m",
        only_strong=True,
        sentiment_mode="negative",
        stop_loss_pct=5.0,
        take_profit_pct=10.0,
        max_trades_day=20,
    )

    def _tech(window):
        current_price = float(window["close"].iloc[-1])
        return TechnicalResult(
            signal="PUT",
            reason="mock-put",
            rsi=82.0,
            macd=-5.0,
            macd_signal=-3.0,
            ema50=current_price + 5,
            bb_upper=current_price + 2,
            bb_lower=current_price - 5,
            current_price=current_price,
        )

    with patch.object(engine.ta, "analyze", side_effect=_tech):
        result = engine.run(df)

    assert result.total_trades >= 1
    assert any(t.direction == "PUT" for t in result.trades)
    assert any((t.pnl_pct or 0) > 0 for t in result.trades), "Esperava pelo menos um PUT lucrativo com preço em queda"
