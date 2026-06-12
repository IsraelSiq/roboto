import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from backend.core.trade import Trade

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
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
    trades: List[Trade]
    equity_curve: List[tuple]

    def summary(self) -> str:
        return (
            f"Backtest {self.symbol} {self.interval}\n"
            f"Período: {self.start_date} → {self.end_date}\n"
            f"Balanço inicial: ${self.initial_balance:,.2f}\n"
            f"Balanço final:   ${self.final_balance:,.2f}\n"
            f"PnL total:       {self.total_pnl_pct:+.2f}%\n"
            f"Trades:          {self.total_trades} (Wins: {self.wins}, Losses: {self.losses}, Win rate: {self.win_rate:.1f}%)\n"
            f"Profit factor:   {self.profit_factor:.2f}\n"
            f"Max drawdown:    {self.max_drawdown:.2f}%\n"
            f"Sharpe ratio:    {self.sharpe_ratio:.2f}\n"
            f"Approved:        {self.approved}"
        )


class BacktestEngine:
    def __init__(
        self,
        symbol: str,
        interval: str,
        balance: float = 10000.0,
        only_strong: bool = True,
        stop_loss_pct: float = 1.0,
        take_profit_pct: float = 2.0,
        sentiment_mode: str = "positive",
        use_atr_stop: bool = False,
        atr_multiplier: float = 1.5,
        rr_ratio: float = 2.0,
        macro_filter_enabled: bool = False,
        macro_resample_tf: str = "1h",
    ):
        self.symbol = symbol
        self.interval = interval
        self.initial_balance = balance
        self.only_strong = only_strong
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.sentiment_mode = sentiment_mode
        self.use_atr_stop = use_atr_stop
        self.atr_multiplier = atr_multiplier
        self.rr_ratio = rr_ratio
        self.macro_filter_enabled = macro_filter_enabled
        self.macro_resample_tf = macro_resample_tf

        self.trades: List[Trade] = []
        self.equity_curve: List[tuple] = []

    def _compute_position_size(self, balance: float, atr: Optional[float] = None) -> float:
        risk_pct = 1.0
        if self.use_atr_stop and atr is not None:
            stop_distance_pct = atr * self.atr_multiplier
        else:
            stop_distance_pct = self.stop_loss_pct

        risk_amount = balance * (risk_pct / 100.0)
        if stop_distance_pct <= 0:
            return 0.0

        position_size = risk_amount / (stop_distance_pct / 100.0)
        return max(position_size, 0.0)

    def _apply_macro_filter(self, df: pd.DataFrame) -> pd.Series:
        if not self.macro_filter_enabled:
            return pd.Series(True, index=df.index)

        close = df["close"]
        macro_trend = close.rolling(50).mean() - close.rolling(200).mean()
        return macro_trend > 0

    def run(self, df: pd.DataFrame) -> BacktestResult:
        if df.empty:
            raise ValueError("DataFrame de candles vazio no backtest.")

        balance = self.initial_balance
        equity_curve: List[tuple] = []

        macro_ok = self._apply_macro_filter(df)

        open_positions: List[Trade] = []

        for idx, row in df.iterrows():
            price = row["close"]
            signal = row.get("signal", 0)
            strength = row.get("strength", "strong")
            atr = row.get("atr", None)

            open_positions = [p for p in open_positions if not p.is_closed]

            for position in open_positions:
                position.update(price)

            open_positions = [p for p in open_positions if not p.is_closed]

            current_equity = balance + sum(p.unrealized_pnl for p in open_positions)
            equity_curve.append((idx, current_equity))

            if not macro_ok.loc[idx]:
                continue

            if self.only_strong and strength != "strong":
                continue

            if signal == 0:
                continue

            size = self._compute_position_size(balance, atr)
            if size <= 0:
                continue

            direction = "LONG" if signal > 0 else "SHORT"
            trade = Trade(
                direction=direction,
                entry_price=price,
                size=size,
                stop_loss_pct=self.stop_loss_pct,
                take_profit_pct=self.take_profit_pct,
                use_atr_stop=self.use_atr_stop,
                atr_multiplier=self.atr_multiplier,
                rr_ratio=self.rr_ratio,
            )
            open_positions.append(trade)
            self.trades.append(trade)

        for position in open_positions:
            if not position.is_closed:
                position.close(df["close"].iloc[-1])

        balance = self.initial_balance + sum(t.realized_pnl for t in self.trades)
        equity_curve.append((df.index[-1], balance))

        prices = df["close"].astype(float)
        returns = prices.pct_change().dropna()
        mean_return = returns.mean() * 252
        std_return = returns.std() * np.sqrt(252)
        sharpe_ratio = mean_return / std_return if std_return != 0 else 0.0

        wins = sum(1 for t in self.trades if t.result == "WIN")
        losses = sum(1 for t in self.trades if t.result == "LOSS")
        win_rate = (wins / self.trades.__len__()) * 100.0 if self.trades else 0.0

        gross_profit = sum(t.realized_pnl for t in self.trades if t.realized_pnl > 0)
        gross_loss = -sum(t.realized_pnl for t in self.trades if t.realized_pnl < 0)
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else 0.0

        peak = -np.inf
        max_drawdown = 0.0
        for _, equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        total_pnl_pct = (balance / self.initial_balance - 1.0) * 100.0
        approved = total_pnl_pct > 0 and win_rate >= 50 and profit_factor >= 1.2

        start_date = str(df.index[0])
        end_date = str(df.index[-1])

        result = BacktestResult(
            symbol=self.symbol,
            interval=self.interval,
            start_date=start_date,
            end_date=end_date,
            initial_balance=self.initial_balance,
            final_balance=balance,
            total_candles=len(df),
            total_signals=sum(1 for _ in df.itertuples() if getattr(_, "signal", 0) != 0),
            total_trades=len(self.trades),
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            total_pnl_pct=total_pnl_pct,
            approved=approved,
            trades=self.trades,
            equity_curve=equity_curve,
        )

        self.equity_curve = equity_curve
        return result
