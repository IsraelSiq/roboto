"""
Roboto — Backtest Engine
Roda a estratégia completa (técnico + sentiment simulado) sobre dados históricos.

Melhorias:
    - Circuit breaker NÃO pausa o backtest: rm.resume() automático
    - window lazy (só copia quando vai analisar)
    - Intracandle SL/TP: verifica high/low do candle, não só close
    - sentiment_mode 'both': alterna positive/negative para gerar CALL e PUT
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from backend.analysis.technical import TechnicalAnalyzer
from backend.analysis.signals import SignalCombiner
from backend.analysis.sentiment import SentimentResult
from backend.analysis.macro_filter import MacroTrendFilter
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
    score: int = 0
    criteria_detail: dict = field(default_factory=dict)
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)

    def summary(self) -> str:
        status = "✅ APROVADO" if self.approved else "❌ REPROVADO"
        pnl_emoji = "📈" if self.total_pnl_pct > 0 else "📉"
        detail = ""
        if self.criteria_detail:
            c = self.criteria_detail
            detail = (
                f"\n  Critérios  : "
                f"WR={'OK' if c.get('win_rate') else 'FAIL'} "
                f"PF={'OK' if c.get('profit_factor') else 'FAIL'} "
                f"DD={'OK' if c.get('drawdown') else 'FAIL'} "
                f"SH={'OK' if c.get('sharpe') else 'FAIL'} "
                f"({self.score}/4 — mínimo 3)"
            )
        return (
            f"\n{'='*55}\n"
            f"  Backtest {self.symbol} {self.interval} — {status}\n"
            f"{'='*55}\n"
            f"  Período     : {self.start_date} → {self.end_date}\n"
            f"  Candles     : {self.total_candles:,}\n"
            f"  Sinais      : {self.total_signals}\n"
            f"  Trades      : {self.total_trades} ({self.wins}W / {self.losses}L){detail}\n"
            f"  Win Rate    : {self.win_rate:.1f}% (meta: ≥ 50%)\n"
            f"  Profit F.   : {self.profit_factor:.2f} (meta: > 1.1)\n"
            f"  Drawdown    : {self.max_drawdown:.1f}% (meta: < 25%)\n"
            f"  Sharpe      : {self.sharpe_ratio:.2f} (meta: > 0.5)\n"
            f"  {pnl_emoji} PnL total   : {self.total_pnl_pct:+.2f}%\n"
            f"  Saldo final : ${self.final_balance:,.2f} (inicial: ${self.initial_balance:,.2f})\n"
            f"{'='*55}"
        )


class BacktestEngine:
    """
    Simula o bot sobre dados históricos candle a candle.

    sentiment_mode aceita:
        'positive' — só CALL_FORTE
        'negative' — só PUT_FORTE
        'neutral'  — sinais fracos
        'both'     — alterna positive/negative a cada janela (padrão)
    """

    VALID_SENTIMENT_MODES = {"neutral", "positive", "negative", "both"}

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "5m",
        balance: float = 10000.0,
        only_strong: bool = True,
        stop_loss_pct: float = 5.0,
        take_profit_pct: float = 10.0,
        max_trades_day: int = 10,
        sentiment_mode: str = "both",
        use_atr_stop: bool = False,
        atr_multiplier: float = 1.5,
        rr_ratio: float = 2.0,
        macro_filter_enabled: bool = False,
        macro_resample_tf: str = "1h",
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
        self.use_atr_stop = use_atr_stop
        self.atr_multiplier = atr_multiplier
        self.rr_ratio = rr_ratio
        self.macro_filter_enabled = macro_filter_enabled
        self.macro_resample_tf = macro_resample_tf
        self._signal_flip = False

        self.ta = TechnicalAnalyzer()
        self.macro_filter = (
            MacroTrendFilter(enabled=True) if macro_filter_enabled
            else MacroTrendFilter(enabled=False)
        )
        self.combiner = SignalCombiner(
            symbol=symbol, timeframe=interval,
            macro_filter=self.macro_filter,
        )
        self._sentiments = {
            mode: SentimentResult(
                signal=mode,
                score=0.85 if mode != "neutral" else 0.50,
                news_count=0,
                reason=f"backtest/{mode}",
                source="backtest_mock",
                raw_scores=self._build_mock_raw_scores(mode),
            )
            for mode in ("positive", "negative", "neutral")
        }

    @staticmethod
    def _build_mock_raw_scores(mode: str) -> dict:
        if mode == "positive":
            return {"positive": 0.85, "negative": 0.10, "neutral": 0.05}
        if mode == "negative":
            return {"positive": 0.10, "negative": 0.85, "neutral": 0.05}
        return {"positive": 0.20, "negative": 0.20, "neutral": 0.60}

    def _get_sentiment(self) -> SentimentResult:
        """No modo 'both', alterna positive/negative a cada avaliação."""
        if self.sentiment_mode == "both":
            self._signal_flip = not self._signal_flip
            return self._sentiments["positive" if self._signal_flip else "negative"]
        return self._sentiments[self.sentiment_mode]

    def _resample_to_macro(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            df = df.copy()
            df["open_time"] = pd.to_datetime(df["open_time"])
            df = df.set_index("open_time")
            resample_map = {"1h": "1h", "4h": "4h", "1d": "D"}
            rule = resample_map.get(self.macro_resample_tf, self.macro_resample_tf)
            macro = df["close"].resample(rule).last().dropna().reset_index()
            macro.columns = ["open_time", "close"]
            return macro
        except Exception as e:
            logger.warning(f"[Backtest] Erro ao reamostrar para macro: {e}")
            return pd.DataFrame()

    def _check_exit_intracandle(self, trade: Trade, candle: pd.Series) -> Optional[str]:
        """
        Verifica SL/TP usando high/low do candle (intracandle).
        Em caso de ambos atingidos no mesmo candle, assume SL (pior caso conservador).
        Faz fallback para close se high/low não estiverem disponíveis.
        """
        try:
            high = float(candle["high"])
            low  = float(candle["low"])
        except (KeyError, TypeError, ValueError):
            close = float(candle["close"])
            if trade.direction == "CALL":
                if close <= trade.stop_loss:   return "SL"
                if close >= trade.take_profit: return "TP"
            else:
                if close >= trade.stop_loss:   return "SL"
                if close <= trade.take_profit: return "TP"
            return None

        if trade.direction == "CALL":
            if low  <= trade.stop_loss:   return "SL"
            if high >= trade.take_profit: return "TP"
        else:
            if high >= trade.stop_loss:   return "SL"
            if low  <= trade.take_profit: return "TP"
        return None

    def run(self, df: pd.DataFrame) -> BacktestResult:
        if df.empty or len(df) < MIN_CANDLES:
            raise ValueError(f"DataFrame insuficiente: {len(df)} candles (mínimo: {MIN_CANDLES})")

        rm = RiskManager(
            balance=self.initial_balance,
            stop_loss_pct=self.stop_loss_pct,
            take_profit_pct=self.take_profit_pct,
            max_trades_day=self.max_trades_day,
            only_strong=self.only_strong,
            use_atr_stop=self.use_atr_stop,
            atr_multiplier=self.atr_multiplier,
            rr_ratio=self.rr_ratio,
        )

        total_signals = 0
        equity_curve  = []
        open_trade: Optional[Trade] = None

        start_date = str(df["open_time"].iloc[MIN_CANDLES])
        end_date   = str(df["open_time"].iloc[-1])

        logger.info(
            f"[Backtest] Iniciando {self.symbol} {self.interval} "
            f"| {len(df):,} candles | sentiment={self.sentiment_mode} "
            f"| atr={self.use_atr_stop} | macro={self.macro_filter_enabled}"
        )

        for i in range(MIN_CANDLES, len(df)):
            current_candle = df.iloc[i]
            current_price  = float(current_candle["close"])
            ts             = str(current_candle["open_time"])
            candle_date    = pd.Timestamp(current_candle["open_time"]).date()

            # Fecha trade com verificação intracandle (high/low)
            if open_trade is not None:
                exit_reason = self._check_exit_intracandle(open_trade, current_candle)
                if exit_reason == "SL":
                    rm.close_trade(open_trade, open_trade.stop_loss)
                    open_trade = None
                elif exit_reason == "TP":
                    rm.close_trade(open_trade, open_trade.take_profit)
                    open_trade = None

            equity_curve.append((ts, rm.balance))

            if i % 5 != 0:
                continue

            # Backtest nunca fica pausado — resume automático
            if rm.is_paused():
                logger.debug(f"[Backtest] Circuit breaker em {ts} — resumindo automático")
                rm.resume()

            window = df.iloc[:i + 1]

            df_macro = None
            if self.macro_filter_enabled:
                df_macro = self._resample_to_macro(window)

            try:
                tech = self.ta.analyze(window)
            except Exception as e:
                logger.debug(f"[Backtest] Erro técnico no candle {i}: {e}")
                continue

            sentiment = self._get_sentiment()

            try:
                decision = self.combiner.combine(tech, sentiment, df_macro=df_macro)
            except Exception as e:
                logger.debug(f"[Backtest] Erro ao combinar sinais: {e}")
                continue

            total_signals += 1

            if open_trade is None:
                ok, reason = rm.can_trade(decision, current_date=candle_date)
                if ok:
                    open_trade = rm.open_trade(decision, current_date=candle_date)
                    logger.debug(
                        f"[Backtest] Trade aberto: {open_trade.direction} "
                        f"entry={open_trade.entry_price:.2f} "
                        f"sl={open_trade.stop_loss:.2f} tp={open_trade.take_profit:.2f}"
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
            score=metrics.score,
            criteria_detail=metrics.criteria_detail,
            trades=rm.closed_trades,
            equity_curve=equity_curve,
        )

        logger.info(result.summary())
        return result
