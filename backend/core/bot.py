"""
Roboto — Bot Principal (Fase 6)
Loop automático que une todos os módulos:
    Binance → Técnico → Sentiment → Sinal → RiskManager → Trade → Métricas

Uso:
    python -m backend.core.bot
    python -m backend.core.bot --symbol ETHUSDT --interval 1m --cycles 5
"""

import argparse
import logging
import time
from datetime import datetime, timezone

from backend.market.binance_client import BinanceClient
from backend.analysis.technical import TechnicalAnalysis
from backend.analysis.sentiment import SentimentAnalysis
from backend.analysis.signals import SignalEngine
from backend.risk.manager import RiskManager
from backend.risk.metrics import PerformanceMetrics

logger = logging.getLogger(__name__)


INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
}


class RobotoBot:
    """
    Orquestra o ciclo completo de operação do robô.

    Args:
        symbol:          Par de moedas (padrão: BTCUSDT)
        interval:        Timeframe dos candles (padrão: 5m)
        candle_limit:    Qtd de candles para análise técnica (padrão: 100)
        balance:         Saldo inicial simulado em USDT (padrão: 10000.0)
        sleep_seconds:   Intervalo entre ciclos em segundos (None = usa o do timeframe)
        only_strong:     Só opera sinais FORTES (padrão: True)
        max_cycles:      Limite de ciclos (None = infinito)
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "5m",
        candle_limit: int = 100,
        balance: float = 10000.0,
        sleep_seconds: int = None,
        only_strong: bool = True,
        max_cycles: int = None,
    ):
        self.symbol = symbol
        self.interval = interval
        self.candle_limit = candle_limit
        self.max_cycles = max_cycles
        self.sleep_seconds = sleep_seconds or INTERVAL_SECONDS.get(interval, 300)

        # Componentes
        self.client = BinanceClient()
        self.technical = TechnicalAnalysis()
        self.sentiment = SentimentAnalysis()
        self.signal_engine = SignalEngine()
        self.risk = RiskManager(
            balance=balance,
            only_strong=only_strong,
        )

        self._cycle = 0
        self._running = False

    # ----------------------------------------------------------
    # LOOP PRINCIPAL
    # ----------------------------------------------------------

    def run(self):
        """Inicia o loop automático do robô."""
        self._running = True
        logger.info(f"[Bot] Iniciando Roboto | {self.symbol} {self.interval} | saldo=${self.risk.balance:,.2f}")
        self._print_header()

        try:
            while self._running:
                if self.max_cycles and self._cycle >= self.max_cycles:
                    logger.info(f"[Bot] Limite de {self.max_cycles} ciclos atingido. Encerrando.")
                    break

                self._cycle += 1
                self._run_cycle()

                if self.risk.is_paused():
                    logger.warning(f"[Bot] Bot pausado pelo RiskManager. Aguardando intervenção manual.")
                    self._print_metrics()
                    break

                if self.max_cycles and self._cycle < self.max_cycles:
                    logger.info(f"[Bot] Aguardando {self.sleep_seconds}s até próximo ciclo...")
                    time.sleep(self.sleep_seconds)

        except KeyboardInterrupt:
            logger.info("[Bot] Interrompido pelo usuário (Ctrl+C).")
        finally:
            self._running = False
            self._print_metrics()

    def stop(self):
        self._running = False

    # ----------------------------------------------------------
    # CICLO
    # ----------------------------------------------------------

    def _run_cycle(self):
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        logger.info(f"[Ciclo {self._cycle}] ─── {now} UTC ──────────────────────")

        # 1. Monitorar trade aberto (SL/TP)
        if self.risk._open_trade:
            self._monitor_open_trade()
            return  # aguarda fechar antes de novo sinal

        # 2. Coleta candles
        candles = self._fetch_candles()
        if candles is None:
            return

        current_price = float(candles[-1][4])  # close do último candle

        # 3. Análise técnica
        tech_signal = self._run_technical(candles)
        if tech_signal is None:
            return

        # 4. Sentiment
        sent_signal, sent_score, news_count = self._run_sentiment()

        # 5. Gera sinal combinado
        decision = self.signal_engine.decide(
            technical_signal=tech_signal["signal"],
            sentiment_signal=sent_signal,
            sentiment_score=sent_score,
            current_price=current_price,
            rsi=tech_signal["rsi"],
            symbol=self.symbol,
            timeframe=self.interval,
            news_count=news_count,
        )

        logger.info(f"[Ciclo {self._cycle}] {decision}")

        # 6. Verifica risk
        ok, reason = self.risk.can_trade(decision)
        if not ok:
            logger.info(f"[Ciclo {self._cycle}] Trade bloqueado: {reason}")
            return

        # 7. Abre trade
        trade = self.risk.open_trade(decision)
        logger.info(
            f"[Ciclo {self._cycle}] 🟢 Trade aberto | {trade.direction} @ ${trade.entry_price:,.2f} "
            f"| SL=${trade.stop_loss:,.2f} | TP=${trade.take_profit:,.2f}"
        )

    # ----------------------------------------------------------
    # MONITORAMENTO DE TRADE ABERTO
    # ----------------------------------------------------------

    def _monitor_open_trade(self):
        trade = self.risk._open_trade
        try:
            ticker = self.client.get_ticker(self.symbol)
            current_price = float(ticker["price"])
        except Exception as e:
            logger.error(f"[Monitor] Erro ao obter preço: {e}")
            return

        exit_reason = self.risk.check_exit(trade, current_price)
        if exit_reason:
            self.risk.close_trade(trade, current_price)
            emoji = "✅" if trade.result == "WIN" else "❌"
            logger.info(
                f"[Monitor] {emoji} Trade fechado por {exit_reason} | "
                f"{trade.pnl_summary()} | Saldo: ${self.risk.balance:,.2f}"
            )
        else:
            logger.info(
                f"[Monitor] Trade em aberto | {trade.direction} @ ${trade.entry_price:,.2f} "
                f"→ atual ${current_price:,.2f} | SL=${trade.stop_loss:,.2f} | TP=${trade.take_profit:,.2f}"
            )

    # ----------------------------------------------------------
    # HELPERS
    # ----------------------------------------------------------

    def _fetch_candles(self):
        try:
            candles = self.client.get_klines(
                symbol=self.symbol,
                interval=self.interval,
                limit=self.candle_limit,
            )
            logger.info(f"[Ciclo {self._cycle}] {len(candles)} candles recebidos")
            return candles
        except Exception as e:
            logger.error(f"[Ciclo {self._cycle}] Erro ao coletar candles: {e}")
            return None

    def _run_technical(self, candles):
        try:
            result = self.technical.analyze(candles)
            logger.info(
                f"[Ciclo {self._cycle}] Técnico: {result['signal']} "
                f"| RSI={result['rsi']:.2f} | MACD={result['macd_cross']} | EMA={result['ema_position']}"
            )
            return result
        except Exception as e:
            logger.error(f"[Ciclo {self._cycle}] Erro na análise técnica: {e}")
            return None

    def _run_sentiment(self):
        try:
            result = self.sentiment.analyze(self.symbol)
            signal = result.get("signal", "neutral")
            score = result.get("score", 0.5)
            count = result.get("count", 0)
            logger.info(f"[Ciclo {self._cycle}] Sentiment: {signal} (score={score:.2f}, {count} notícias)")
            return signal, score, count
        except Exception as e:
            logger.warning(f"[Ciclo {self._cycle}] Erro no sentiment (usando neutral): {e}")
            return "neutral", 0.5, 0

    def _print_header(self):
        print("\n" + "="*58)
        print(f"  🤖 Roboto — {self.symbol} {self.interval}")
        print(f"  Saldo inicial : ${self.risk.initial_balance:,.2f}")
        print(f"  Stop Loss     : {self.risk.stop_loss_pct}%")
        print(f"  Take Profit   : {self.risk.take_profit_pct}%")
        print(f"  Max trades/dia: {self.risk.max_trades_day}")
        print(f"  Max drawdown  : {self.risk.max_drawdown_pct}%")
        print(f"  Only strong   : {self.risk.only_strong}")
        print(f"  Ciclos        : {self.max_cycles or '∞'}")
        print("="*58 + "\n")

    def _print_metrics(self):
        trades = self.risk.closed_trades
        status = self.risk.status()
        print("\n" + "="*58)
        print("  📊 Resumo Final")
        print("="*58)
        print(f"  Saldo final   : ${status['balance']:,.2f}")
        print(f"  Drawdown atual: {status['drawdown_pct']:.1f}%")
        print(f"  Trades hoje   : {status['trades_today']}")
        print(f"  Total trades  : {status['total_trades']}")
        if trades:
            metrics = PerformanceMetrics(trades)
            result = metrics.calculate()
            print(result.summary())
        else:
            print("  Nenhum trade fechado nesta sessão.")
        print("="*58 + "\n")


# ----------------------------------------------------------
# Entry point
# ----------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Roboto — Bot de trading automático")
    parser.add_argument("--symbol",   default="BTCUSDT", help="Par de moedas (padrão: BTCUSDT)")
    parser.add_argument("--interval", default="5m",      help="Timeframe (padrão: 5m)")
    parser.add_argument("--balance",  default=10000.0,   type=float, help="Saldo inicial USDT")
    parser.add_argument("--cycles",   default=3,         type=int,   help="Nº de ciclos (padrão: 3, 0=infinito)")
    parser.add_argument("--sleep",    default=0,         type=int,   help="Seg entre ciclos (0=usa timeframe)")
    parser.add_argument("--weak",     action="store_true",           help="Aceita sinais FRACOS também")
    args = parser.parse_args()

    bot = RobotoBot(
        symbol=args.symbol,
        interval=args.interval,
        balance=args.balance,
        sleep_seconds=args.sleep if args.sleep > 0 else None,
        only_strong=not args.weak,
        max_cycles=args.cycles if args.cycles > 0 else None,
    )
    bot.run()
