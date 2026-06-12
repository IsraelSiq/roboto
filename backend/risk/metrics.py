import numpy as np


def max_drawdown(equity_curve: list[tuple]) -> float:
    """Calcula o máximo drawdown em porcentagem a partir de uma curva de equity."""
    if not equity_curve:
        return 0.0

    equities = np.array([e for _, e in equity_curve], dtype=float)
    peaks = np.maximum.accumulate(equities)
    drawdowns = (peaks - equities) / peaks * 100.0
    return float(drawdowns.max())


def sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.0) -> float:
    """Calcula o Sharpe Ratio anualizado para uma série de retornos diários."""
    if returns.size == 0:
        return 0.0

    excess_returns = returns - risk_free_rate
    mean_return = excess_returns.mean() * 252
    std_return = excess_returns.std() * np.sqrt(252)
    if std_return == 0:
        return 0.0
    return float(mean_return / std_return)
