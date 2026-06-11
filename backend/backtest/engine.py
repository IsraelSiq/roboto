"""
Roboto — Backtest Engine
Roda a estratégia completa (técnico + sentiment simulado) sobre dados históricos.

Issue #6:
    - Valida explicitamente suporte a PUT no backtest
    - Mantém compatibilidade com o novo SentimentResult (source/raw_scores)
    - Permite simular sentiment negative para gerar PUT_FORTE
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from backend.analysis.technical import TechnicalAnalyzer
from backend.analysis.signals import SignalCombiner, SignalDecision
from backend.analysis.sentiment import SentimentResult
from backend.risk.manager import RiskManager, Trade
from backend.risk.metrics import PerformanceMetrics

logger = logging.getLogger(__name__)

MIN_CANDLES = 60


@dataclass
class BacktestResult:
    """Resultado completo de um backtest."""
    symbol: str
    interval: str
    start_date: str
    end_date: str
    initial_balance: float
    final_balance: float
    total_candles: int
    total_signals: int
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    total_pnl_pct: float
    approved: bool
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)

    def summary(self) -> str:
        status = "✅ APROVADO" if self.approved else "❌ REPROVADO"
        pnl_emoji = "📈" if self.total_pnl_pct > 0 else "📉"
        return (
            f"\n{'='*55}\n"
            f"  Backtest {self.symbol} {self.interval} — {status}\n"
            f"{'='*55}\n"
            f"  Período     : {self.start_date} → {self.end_date}\n"
            f"  Candles     : {self.total_candles:,}\n"
            f"  Sinais      : {self.total_signals}\n"
            f"  Trades      : {self.total_trades} ({self.wins}W / {self.losses}L)\n"
            f"  Win Rate    : {self.win_rate:.1f}% (meta: ≥ 65%)\n"
            f"  Profit F.   : {self.profit_factor:.2f} (meta: > 1.5)\n"
            f"  Drawdown    : {self.max_drawdown:.1f}% (meta: < 20%)\n"
            f"  Sharpe      : {self.sharpe_ratio:.2f} (meta: > 1.0)\n"
            f"  {pnl_emoji} PnL total   : {self.total_pnl_pct:+.2f}%\n"
            f"  Saldo final : ${self.final_balance:,.2f} (inicial: ${self.initial_balance:,.2f})\n"
            f"{'='*55}"
        )


class BacktestEngine:
    """
    Simula o bot sobre dados históricos candle a candle.

    Args:
        symbol:          Par de trading
        interval:        Timeframe
        balance:         Saldo inicial
        only_strong:     Apenas sinais FORTES (padrão: True)
        stop_loss_pct:   Stop loss % (padrão: 5.0)
        take_profit_pct: Take profit % (padrão: 10.0)
        max_trades_day:  Máximo de trades por dia
        sentiment_mode:  'neutral' | 'positive' | 'negative' (padrão: 'positive')
    """

    VALID_SENTIMENT_MODES = {"neutral", "positive", "negative"}

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "5m",
        balance: float = 10000.0,
        only_strong: bool = True,
        stop_loss_pct: float = 5.0,
        take_profit_pct: float = 10.0,
        max_trades_day: int = 10,
        sentiment_mode: str = "positive",
    ):
        if sentiment_mode not in self.VALID_SENTIMENT_MODES:
            raise ValueError(
                f"sentiment_mode inválido: {sentiment_mode}. "
                f"Use um de {sorted(self.VALID_SENTIMENT_MODES)}"
            )

        self.symbol = symbol
        self.interval = interval
        self.initial_balance = balance
        self.only_strong = only_strong
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_trades_day = max_trades_day
        self.sentiment_mode = sentiment_mode

        self.ta = TechnicalAnalyzer()
        self.combiner = SignalCombiner(symbol=symbol, timeframe=interval)

        self._sentiment = SentimentResult(
            signal=sentiment_mode,
            score=0.85 if sentiment_mode != "neutral" else 0.50,
            news_count=0,
            reason=f"backtest/{sentiment_mode}",
            source="backtest_mock",
            raw_scores=self._build_mock_raw_scores(sentiment_mode),
        )

    @staticmethod
    def _build_mock_raw_scores(mode: str) -> dict:
        if mode == "positive":
            return {"positive": 0.85, "negative": 0.10, "neutral": 0.05}
        if mode == "negative":
            return {"positive": 0.10, "negative": 0.85, "neutral": 0.05}
        return {"positive": 0.20, "negative": 0.20, "neutral": 0.60}

    def run(self, df: pd.DataFrame) -> BacktestResult:
        if df.empty or len(df) < MIN_CANDLES:
            raise ValueError(f"DataFrame insuficiente: {len(df)} candles (mínimo: {MIN_CANDLES})")

        rm = RiskManager(
            balance=self.initial_balance,
            stop_loss_pct=self.stop_loss_pct,
            take_profit_pct=self.take_profit_pct,
            max_trades_day=self.max_trades_day,
            only_strong=self.only_strong,
        )

        total_signals = 0
        equity_curve = []
        open_trade: Optional[Trade] = None

        start_date = str(df["open_time"].iloc[MIN_CANDLES])
        end_date = str(df["open_time"].iloc[-1])

        logger.info(
            f"[Backtest] Iniciando {self.symbol} {self.interval} "
            f"| {len(df):,} candles | sentiment={self.sentiment_mode}"
        )

        for i in range(MIN_CANDLES, len(df)):
            window = df.iloc[:i+1].copy()
            current_candle = df.iloc[i]
            current_price = float(current_candle["close"])
            ts = str(current_candle["open_time"])
            candle_date = pd.Timestamp(current_candle["open_time"]).date()

            if open_trade is not None:
                exit_reason = rm.check_exit(open_trade, current_price)
                if exit_reason == "SL":
                    rm.close_trade(open_trade, open_trade.stop_loss)
                    open_trade = None
                elif exit_reason == "TP":
                    rm.close_trade(open_trade, open_trade.take_profit)
                    open_trade = None

            equity_curve.append((ts, rm.balance))

            if i % 5 != 0:
                continue

            if rm.is_paused():
                continue

            try:
                tech = self.ta.analyze(window)
            except Exception as e:
                logger.debug(f"[Backtest] Erro técnico no candle {i}: {e}")
                continue

            try:
                decision = self.combiner.combine(tech, self._sentiment)
            except Exception as e:
                logger.debug(f"[Backtest] Erro ao combinar sinais: {e}")
                continue

            total_signals += 1

            if open_trade is None:
                ok, reason = rm.can_trade(decision, current_date=candle_date)
                if ok:
                    open_trade = rm.open_trade(decision, current_date=candle_date)
                    logger.debug(
                        f"[Backtest] Trade aberto: direction={open_trade.direction} "
                        f"entry={open_trade.entry_price} sl={open_trade.stop_loss} tp={open_trade.take_profit}"
                    )

        if open_trade is not None:
            rm.close_trade(open_trade, float(df["close"].iloc[-1]))

        metrics = PerformanceMetrics(rm.closed_trades).calculate()

        result = BacktestResult(
            symbol=self.symbol,
            interval=self.interval,
            start_date=start_date,
            end_date=end_date,
            initial_balance=self.initial_balance,
            final_balance=rm.balance,
            total_candles=len(df),
            total_signals=total_signals,
            total_trades=metrics.total_trades,
            wins=metrics.wins,
            losses=metrics.losses,
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            max_drawdown=metrics.max_drawdown,
            sharpe_ratio=metrics.sharpe_ratio,
            total_pnl_pct=metrics.total_pnl_pct,
            approved=metrics.approved,
            trades=rm.closed_trades,
            equity_curve=equity_curve,
        )

        logger.info(result.summary())
        return result
