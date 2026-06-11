"""
Roboto — Filtro de Tendência Macro (multi-timeframe)
Issue #8

Evita operar contra o fluxo dominante do mercado:
    - CALL bloqueado quando tendência macro (1h) é de baixa
    - PUT  bloqueado quando tendência macro (1h) é de alta

Estratégia:
    tendência de ALTA:  preço_atual > EMA_fast > EMA_slow
    tendência de BAIXA: preço_atual < EMA_fast < EMA_slow
    LATERAL (ou dados insuficientes): bloqueia ambos (retorna None)

Uso:
    from backend.analysis.macro_filter import MacroTrendFilter
    filtro = MacroTrendFilter()
    resultado = filtro.tendencia_favoravel(df_1h, direcao='CALL')
    # True  → pode entrar
    # False → bloqueado
    # None  → indeterminado (dados insuficientes / lateral)
"""

import logging
from typing import Optional

import pandas as pd
import pandas_ta_classic as ta

logger = logging.getLogger(__name__)


class MacroTrendFilter:
    """
    Filtro de tendência baseado em EMA dupla no timeframe macro.

    Args:
        ema_fast:       Período da EMA rápida (padrão: 20)
        ema_slow:       Período da EMA lenta (padrão: 50)
        min_candles:    Mínimo de candles para calcular (padrão: 60)
        enabled:        Liga/desliga o filtro (padrão: True)
    """

    def __init__(
        self,
        ema_fast: int = 20,
        ema_slow: int = 50,
        min_candles: int = 60,
        enabled: bool = True,
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.min_candles = min_candles
        self.enabled = enabled

    def tendencia_favoravel(self, df: pd.DataFrame, direcao: str) -> Optional[bool]:
        """
        Verifica se a tendência macro é favorável para a direção do sinal.

        Args:
            df:      DataFrame com candles do timeframe macro (deve ter coluna 'close')
            direcao: 'CALL' ou 'PUT'

        Returns:
            True  — tendência favorável, pode entrar
            False — tendência desfavorável, bloqueado
            None  — indeterminado (dados insuficientes ou mercado lateral)
        """
        if not self.enabled:
            return True

        if df is None or df.empty or len(df) < self.min_candles:
            logger.debug(
                f"[MacroFilter] Dados insuficientes ({len(df) if df is not None else 0}/{self.min_candles}). "
                "Retornando None (sem bloqueio)."
            )
            return None

        try:
            ema_fast_s = ta.ema(df["close"], length=self.ema_fast)
            ema_slow_s = ta.ema(df["close"], length=self.ema_slow)

            if ema_fast_s is None or ema_slow_s is None:
                logger.warning("[MacroFilter] Não foi possível calcular EMAs macro.")
                return None

            ema_fast_val = float(ema_fast_s.iloc[-1])
            ema_slow_val = float(ema_slow_s.iloc[-1])
            preco_atual  = float(df["close"].iloc[-1])

            tendencia_alta  = preco_atual > ema_fast_val > ema_slow_val
            tendencia_baixa = preco_atual < ema_fast_val < ema_slow_val

            logger.debug(
                f"[MacroFilter] preço={preco_atual:.2f} "
                f"EMA{self.ema_fast}={ema_fast_val:.2f} "
                f"EMA{self.ema_slow}={ema_slow_val:.2f} "
                f"| alta={tendencia_alta} baixa={tendencia_baixa} | dir={direcao}"
            )

            if direcao == "CALL":
                if tendencia_alta:
                    return True
                if tendencia_baixa:
                    logger.warning(
                        f"[MacroFilter] ⚠️  CALL BLOQUEADO — tendência macro de BAIXA "
                        f"(preço={preco_atual:.2f} < EMA{self.ema_fast}={ema_fast_val:.2f} "
                        f"< EMA{self.ema_slow}={ema_slow_val:.2f})"
                    )
                    return False
                # Lateral: bloqueio conservador
                logger.debug("[MacroFilter] Mercado lateral — CALL bloqueado conservadoramente.")
                return None

            if direcao == "PUT":
                if tendencia_baixa:
                    return True
                if tendencia_alta:
                    logger.warning(
                        f"[MacroFilter] ⚠️  PUT BLOQUEADO — tendência macro de ALTA "
                        f"(preço={preco_atual:.2f} > EMA{self.ema_fast}={ema_fast_val:.2f} "
                        f"> EMA{self.ema_slow}={ema_slow_val:.2f})"
                    )
                    return False
                logger.debug("[MacroFilter] Mercado lateral — PUT bloqueado conservadoramente.")
                return None

            return None

        except Exception as e:
            logger.error(f"[MacroFilter] Erro ao calcular tendência macro: {e}")
            return None

    def status_str(self, df: pd.DataFrame) -> str:
        """Retorna string de status para logs/header."""
        if not self.enabled:
            return "desativado"
        if df is None or df.empty or len(df) < self.min_candles:
            return f"sem dados ({len(df) if df is not None else 0}/{self.min_candles} candles)"

        try:
            ema_fast_s = ta.ema(df["close"], length=self.ema_fast)
            ema_slow_s = ta.ema(df["close"], length=self.ema_slow)
            f = float(ema_fast_s.iloc[-1])
            s = float(ema_slow_s.iloc[-1])
            p = float(df["close"].iloc[-1])
            if p > f > s:
                return f"ALTA ↑ (preço={p:.0f} > EMA{self.ema_fast}={f:.0f} > EMA{self.ema_slow}={s:.0f})"
            if p < f < s:
                return f"BAIXA ↓ (preço={p:.0f} < EMA{self.ema_fast}={f:.0f} < EMA{self.ema_slow}={s:.0f})"
            return f"LATERAL ↔ (EMA{self.ema_fast}={f:.0f} EMA{self.ema_slow}={s:.0f})"
        except Exception:
            return "erro ao calcular"
