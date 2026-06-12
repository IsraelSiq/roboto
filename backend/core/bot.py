"""
Roboto — Bot Principal
Loop automático que une todos os módulos:
    Binance → Técnico → Macro → Sentiment → Sinal → RiskManager → Trade → Métricas
    + Supabase para persistência de sinais, trades e sessões
    + Telegram para alertas de startup, shutdown, circuit breaker, trades e drawdown

Uso:
    python -m backend.core.bot
    python -m backend.core.bot --symbol ETHUSDT --interval 1m --cycles 5
    python -m backend.core.bot --no-macro
    python -m backend.core.bot --macro-tf 4h
    python -m backend.core.bot --atr-mult 2.0 --rr 2.5
"""

import argparse
import logging
import time
from datetime import datetime, timezone

from backend.market.binance_client import BinanceClient
from backend.analysis.technical import TechnicalAnalyzer
from backend.analysis.sentiment import SentimentAnalyzer
from backend.analysis.signals import SignalCombiner
from backend.analysis.macro_filter import MacroTrendFilter
from backend.risk.manager import RiskManager
from backend.risk.metrics import PerformanceMetrics
from backend.market.symbols import SYMBOL_KEYWORDS
from backend.utils.telegram import TelegramAlert

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = {
    "1m":  60,
    "3m":  180,
    "5m":  300,
    "15m": 900,
    "30m": 1800,
    "1h":  3600,
}


class RobotoBot:
    """
    Orquestra o ciclo completo de operação do robô.

    Args:
        symbol:                 Par de moedas (padrão: BTCUSDT)
        interval:               Timeframe dos candles (padrão: 5m)
        candle_limit:           Qtd de candles para análise técnica (padrão: 100)
        balance:                Saldo inicial simulado em USDT (padrão: 10000.0)
        sleep_seconds:          Intervalo entre ciclos em segundos (0 = sem sleep)
        only_strong:            Só opera sinais FORTES (padrão: True)
        max_cycles:             Limite de ciclos (None = infinito)
        use_db:                 Persiste dados no Supabase (padrão: True)
        max_consecutive_losses: Circuit breaker: pausa após N perdas seguidas (padrão: 3)
        news_limit:             Qtd de notícias para buscar por ciclo (padrão: 5)
        use_atr_stop:           Usa SL adaptativo por ATR (padrão: True)
        atr_multiplier:         Multiplicador do ATR para o SL (padrão: 1.5)
        rr_ratio:               Razão Risco:Recompensa para TP (padrão: 2.0)
        macro_filter_enabled:   Ativa filtro de tendência macro (padrão: True)
        macro_timeframe:        Timeframe do filtro macro (padrão: '1h')
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
        use_db: bool = True,
        max_consecutive_losses: int = 3,
        news_limit: int = 5,
        use_atr_stop: bool = True,
        atr_multiplier: float = 1.5,
        rr_ratio: float = 2.0,
        macro_filter_enabled: bool = True,
        macro_timeframe: str = "1h",
    ):
        self.symbol = symbol
        self.interval = interval
        self.candle_limit = candle_limit
        self.max_cycles = max_cycles
        # fix: sleep_seconds=0 deve ser respeitado (0 é falsy, usar `is not None`)
        self.sleep_seconds = sleep_seconds if sleep_seconds is not None else INTERVAL_SECONDS.get(interval, 300)
        self.keyword = SYMBOL_KEYWORDS.get(symbol, "bitcoin")
        self.news_limit = news_limit
        self.macro_timeframe = macro_timeframe

        self.client = BinanceClient()
        self.technical = TechnicalAnalyzer()
        self.sentiment = SentimentAnalyzer(min_confidence=0.6)

        self.macro_filter = (
            MacroTrendFilter(enabled=True)
            if macro_filter_enabled else
            MacroTrendFilter(enabled=False)
        )

        self.combiner = SignalCombiner(
            symbol=symbol,
            timeframe=interval,
            macro_filter=self.macro_filter,
        )
        self.risk = RiskManager(
            balance=balance,
            only_strong=only_strong,
            max_consecutive_losses=max_consecutive_losses,
            use_atr_stop=use_atr_stop,
            atr_multiplier=atr_multiplier,
            rr_ratio=rr_ratio,
        )
        self.tg = TelegramAlert()

        self.db = None
        self._session_id = None
        if use_db:
            try:
                from backend.db.supabase_client import SupabaseClient
                self.db = SupabaseClient()
            except Exception as e:
                logger.warning(f"[Bot] Supabase indisponível (modo offline): {e}")

        self._cycle = 0
        self._running = False
        self._stop_reason = "encerrado"
        self._df_macro = None

    # ----------------------------------------------------------
    # LOOP PRINCIPAL
    # ----------------------------------------------------------

    def run(self):
        self._running = True
        logger.info(f"[Bot] Iniciando Roboto | {self.symbol} {self.interval} | saldo=${self.risk.balance:,.2f}")
        self._print_header()

        self.tg.startup(
            symbol=self.symbol,
            interval=self.interval,
            balance=self.risk.initial_balance,
            cycles=str(self.max_cycles) if self.max_cycles else "infinito",
        )

        if self.db:
            self._session_id = self.db.create_session(
                symbol=self.symbol,
                interval=self.interval,
                balance=self.risk.initial_balance,
            )

        try:
            while self._running:
                if self.max_cycles and self._cycle >= self.max_cycles:
                    self._stop_reason = f"limite de {self.max_cycles} ciclos atingido"
                    logger.info(f"[Bot] {self._stop_reason.capitalize()}. Encerrando.")
                    break

                self._cycle += 1
                self._run_cycle()

                # --- Alerta de drawdown elevado (#32) ---
                self._check_drawdown_alert()

                if self.risk.is_paused():
                    self._stop_reason = self.risk._pause_reason
                    logger.warning(
                        f"[Bot] ⚠️ Bot pausado pelo RiskManager: {self._stop_reason}. "
                        "Aguardando intervenção manual."
                    )
                    if "Circuit breaker" in self._stop_reason:
                        self.tg.circuit_breaker(
                            consecutive_losses=self.risk._consecutive_losses,
                            balance=self.risk.balance,
                        )
                    break

                if self._running and (self.max_cycles is None or self._cycle < self.max_cycles):
                    if self.sleep_seconds > 0:
                        logger.info(f"[Bot] Aguardando {self.sleep_seconds}s até próximo ciclo...")
                        self._interruptible_sleep(self.sleep_seconds)

        except KeyboardInterrupt:
            self._stop_reason = "Ctrl+C (usuário)"
            logger.info("[Bot] Interrompido pelo usuário (Ctrl+C).")
        except Exception as e:
            self._stop_reason = f"erro inesperado: {e}"
            logger.exception(f"[Bot] Erro inesperado: {e}")
            self.tg.error("loop principal", str(e))
        finally:
            self._running = False

            if self.db and self._session_id:
                self.db.close_session(
                    session_id=self._session_id,
                    balance_end=self.risk.balance,
                    cycles=self._cycle,
                )

            win_rate = None
            closed = self.risk.closed_trades
            if closed:
                wins = sum(1 for t in closed if t.result == "WIN")
                win_rate = wins / len(closed) * 100

            self.tg.shutdown(
                reason=self._stop_reason,
                balance=self.risk.balance,
                cycles=self._cycle,
                win_rate=win_rate,
            )

            self._print_metrics()

    def stop(self):
        self._stop_reason = "stop() chamado externamente"
        self._running = False

    def _interruptible_sleep(self, seconds: float):
        """Sleep interrompido assim que _running vira False (granularidade 0.1s)."""
        deadline = time.monotonic() + seconds
        while self._running and time.monotonic() < deadline:
            time.sleep(min(0.1, deadline - time.monotonic()))

    # ----------------------------------------------------------
    # CICLO
    # ----------------------------------------------------------

    def _run_cycle(self):
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        logger.info(f"[Ciclo {self._cycle}] ─── {now} UTC " + "─" * 22)

        if self.risk._open_trade:
            self._monitor_open_trade()
            return

        df = self._fetch_candles()
        if df is None or df.empty:
            return

        if self.macro_filter.enabled:
            self._df_macro = self._fetch_macro_candles()

        tech = self._run_technical(df)
        if tech is None:
            return

        sent = self._run_sentiment()
        decision = self.combiner.combine(tech, sent, df_macro=self._df_macro)
        logger.info(f"[Ciclo {self._cycle}] {decision.summary()}")

        signal_id = None
        if self.db:
            signal_id = self.db.save_signal({
                "symbol":           self.symbol,
                "interval":         self.interval,
                "final":            decision.final,
                "technical_signal": tech.signal,
                "sentiment_signal": sent.signal,
                "sentiment_score":  sent.score,
                "confidence":       decision.confidence,
                "rsi":              tech.rsi,
                "current_price":    tech.current_price,
                "reason":           decision.reason,
                "cycle":            self._cycle,
                "mode":             "paper",
                "macro_blocked":    decision.macro_blocked,
            })

        ok, reason = self.risk.can_trade(decision)
        if not ok:
            logger.info(f"[Ciclo {self._cycle}] Trade bloqueado: {reason}")
            return

        trade = self.risk.open_trade(decision)
        logger.info(
            f"[Ciclo {self._cycle}] 🟢 Trade aberto | {trade.direction} @ ${trade.entry_price:,.2f} "
            f"| SL=${trade.stop_loss:,.2f} ({trade.stop_loss_mode}) "
            f"| TP=${trade.take_profit:,.2f} | ID={trade.id}"
        )

        if self.db:
            self.db.save_trade(trade, signal_id=signal_id)

    # ----------------------------------------------------------
    # MONITORAMENTO DE TRADE ABERTO
    # ----------------------------------------------------------

    def _monitor_open_trade(self):
        trade = self.risk._open_trade
        try:
            current_price = self.client.get_price(self.symbol)
        except Exception as e:
            logger.error(f"[Monitor] Erro ao obter preço: {e}")
            return

        if current_price is None:
            logger.error(
                f"[Monitor] get_price({self.symbol}) retornou None — "
                "ciclo de monitoramento ignorado (falha na Binance)"
            )
            return

        exit_reason = self.risk.check_exit(trade, current_price)
        if exit_reason:
            self.risk.close_trade(trade, current_price)
            emoji = "✅" if trade.result == "WIN" else "❌"
            logger.info(
                f"[Monitor] {emoji} Trade fechado por {exit_reason} | "
                f"{trade.pnl_summary()} | Saldo: ${self.risk.balance:,.2f}"
            )
            self.tg.trade_closed(
                symbol=trade.symbol,
                direction=trade.direction,
                pnl_pct=trade.pnl_pct or 0.0,
                result=trade.result,
                balance=self.risk.balance,
            )
            if trade.result == "WIN":
                self.tg.reset_drawdown_alert()
                logger.debug("[Bot] reset_drawdown_alert() após WIN")

            if self.db:
                self.db.save_trade(trade)
        else:
            logger.info(
                f"[Monitor] Trade em aberto | {trade.direction} @ ${trade.entry_price:,.2f} "
                f"→ atual ${current_price:,.2f} | SL=${trade.stop_loss:,.2f} | TP=${trade.take_profit:,.2f}"
            )

    # ----------------------------------------------------------
    # DRAWDOWN ALERT (#32)
    # ----------------------------------------------------------

    def _check_drawdown_alert(self):
        """
        Verifica o drawdown atual e dispara alerta Telegram se ultrapassar
        o threshold configurado em DRAWDOWN_ALERT_PCT (padrão: 10%).
        Chamado ao final de cada ciclo, após _run_cycle().
        Anti-spam garantido pelo flag interno de TelegramAlert.
        """
        try:
            status = self.risk.status()
            dd = status.get("drawdown_pct", 0.0) or 0.0
            self.tg.drawdown_alert(
                drawdown_pct=dd,
                balance=self.risk.balance,
                symbol=self.symbol,
            )
        except Exception as e:
            logger.debug(f"[Bot] _check_drawdown_alert erro (ignorando): {e}")

    # ----------------------------------------------------------
    # HELPERS
    # ----------------------------------------------------------

    def _fetch_candles(self):
        try:
            df = self.client.get_candles(
                symbol=self.symbol, interval=self.interval, limit=self.candle_limit,
            )
            logger.info(f"[Ciclo {self._cycle}] {len(df)} candles recebidos")
            return df
        except Exception as e:
            logger.error(f"[Ciclo {self._cycle}] Erro ao coletar candles: {e}")
            return None

    def _fetch_macro_candles(self):
        try:
            df = self.client.get_candles(
                symbol=self.symbol,
                interval=self.macro_timeframe,
                limit=100,
            )
            logger.debug(
                f"[MacroFilter] {len(df)} candles {self.macro_timeframe} recebidos "
                f"| tendência: {self.macro_filter.status_str(df)}"
            )
            return df
        except Exception as e:
            logger.warning(f"[MacroFilter] Erro ao buscar candles {self.macro_timeframe}: {e}")
            return None

    def _run_technical(self, df):
        try:
            result = self.technical.analyze(df)
            logger.info(
                f"[Ciclo {self._cycle}] Técnico: {result.signal} "
                f"| RSI={result.rsi} | MACD={result.macd_cross} | EMA={result.price_vs_ema} "
                f"| ATR={result.atr}"
            )
            return result
        except Exception as e:
            logger.error(f"[Ciclo {self._cycle}] Erro na análise técnica: {e}")
            return None

    def _run_sentiment(self):
        try:
            result = self.sentiment.get_news_sentiment(
                keyword=self.keyword,
                news_limit=self.news_limit,
            )
            logger.info(
                f"[Ciclo {self._cycle}] Sentiment: {result.signal} "
                f"(score={result.score:.2f}, {result.news_count} notícias, source={result.source})"
            )
            return result
        except Exception as e:
            from backend.analysis.sentiment import SentimentResult
            logger.warning(f"[Ciclo {self._cycle}] Erro no sentiment (usando neutral): {e}")
            return SentimentResult(signal="neutral", score=0.5, reason=f"Erro: {e}")

    def _print_header(self):
        sl_mode_str = (
            f"ATR x {self.risk.atr_multiplier} (R:R {self.risk.rr_ratio}:1)"
            if self.risk.use_atr_stop else
            f"Fixo {self.risk.stop_loss_pct}% / TP {self.risk.take_profit_pct}%"
        )
        macro_str = (
            f"ativo ({self.macro_timeframe}) | EMA{self.macro_filter.ema_fast}/EMA{self.macro_filter.ema_slow}"
            if self.macro_filter.enabled else "desativado"
        )
        dd_threshold = getattr(self.tg, "drawdown_threshold", None)
        if dd_threshold is None:
            dd_threshold = getattr(self.tg, "_drawdown_threshold", 0)
        try:
            dd_str = f"{float(dd_threshold):.0f}%"
        except (TypeError, ValueError):
            dd_str = "N/A"

        print("\n" + "="*60)
        print(f"  🤖 Roboto — {self.symbol} {self.interval}")
        print(f"  Saldo inicial    : ${self.risk.initial_balance:,.2f}")
        print(f"  SL / TP          : {sl_mode_str}")
        print(f"  Filtro macro     : {macro_str}")
        print(f"  Max trades/dia   : {self.risk.max_trades_day}")
        print(f"  Max drawdown     : {self.risk.max_drawdown_pct}%")
        print(f"  Circuit breaker  : {self.risk.max_consecutive_losses} perdas consecutivas")
        print(f"  Drawdown alerta  : {dd_str} (Telegram)")
        print(f"  Only strong      : {self.risk.only_strong}")
        print(f"  Ciclos           : {self.max_cycles or 'infinito'}")
        print(f"  Sleep            : {self.sleep_seconds}s entre ciclos")
        print(f"  Notícias/ciclo   : {self.news_limit} (CryptoPanic + RSS)")
        print(f"  Supabase         : {'\u2705 conectado' if self.db else '⚠️  offline'}")
        print(f"  Telegram         : {'\u2705 ativo' if self.tg.enabled else '⚠️  desativado (sem token)'}")
        print("="*60 + "\n")

    def _print_metrics(self):
        trades = self.risk.closed_trades
        status = self.risk.status()
        print("\n" + "="*60)
        print("  📊 Resumo Final")
        print("="*60)
        print(f"  Saldo final         : ${status['balance']:,.2f}")
        print(f"  Drawdown atual      : {status['drawdown_pct']:.1f}%")
        print(f"  Perdas consecutivas : {status['consecutive_losses']}/{status['max_consecutive_losses']}")
        print(f"  Trades hoje         : {status['trades_today']}")
        print(f"  Total trades        : {status['total_trades']}")
        if trades:
            metrics = PerformanceMetrics(trades)
            result = metrics.calculate()
            print(result.summary())
        else:
            print("  Nenhum trade fechado nesta sessão.")
        print("="*60 + "\n")


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
    parser.add_argument("--symbol",      default="BTCUSDT",  help="Par de moedas (padrão: BTCUSDT)")
    parser.add_argument("--interval",    default="5m",       help="Timeframe (padrão: 5m)")
    parser.add_argument("--balance",     default=10000.0,    type=float, help="Saldo inicial USDT")
    parser.add_argument("--cycles",      default=5,          type=int,   help="Nº de ciclos (0=infinito)")
    parser.add_argument("--sleep",       default=30,         type=int,   help="Seg entre ciclos (0=usa timeframe)")
    parser.add_argument("--weak",        action="store_true",            help="Aceita sinais FRACOS também")
    parser.add_argument("--no-db",       action="store_true",            help="Desativa persistência no Supabase")
    parser.add_argument("--max-losses",  default=3,          type=int,   help="Circuit breaker: N perdas consecutivas")
    parser.add_argument("--news-limit",  default=5,          type=int,   help="Notícias por ciclo (padrão: 5)")
    parser.add_argument("--no-atr",      action="store_true",            help="Desativa SL adaptativo ATR (usa % fixo)")
    parser.add_argument("--atr-mult",    default=1.5,        type=float, help="Multiplicador ATR para SL (padrão: 1.5)")
    parser.add_argument("--rr",          default=2.0,        type=float, help="R:R mínimo para TP (padrão: 2.0)")
    parser.add_argument("--no-macro",    action="store_true",            help="Desativa filtro de tendência macro")
    parser.add_argument("--macro-tf",    default="1h",                   help="Timeframe do filtro macro (padrão: 1h)")
    args = parser.parse_args()

    bot = RobotoBot(
        symbol=args.symbol,
        interval=args.interval,
        balance=args.balance,
        sleep_seconds=args.sleep if args.sleep > 0 else None,
        only_strong=not args.weak,
        max_cycles=args.cycles if args.cycles > 0 else None,
        use_db=not args.no_db,
        max_consecutive_losses=args.max_losses,
        news_limit=args.news_limit,
        use_atr_stop=not args.no_atr,
        atr_multiplier=args.atr_mult,
        rr_ratio=args.rr,
        macro_filter_enabled=not args.no_macro,
        macro_timeframe=args.macro_tf,
    )
    bot.run()
