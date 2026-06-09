# Métricas de Avaliação — Roboto

## Por que não basta o win rate?

Um robô pode ter 70% de win rate e ainda perder dinheiro se as perdas forem maiores que os ganhos.
Por isso, avaliamos um conjunto de métricas.

---

## Métricas utilizadas

| Métrica | Definição | Meta |
|---|---|---|
| **Win Rate** | % de trades vencedores | ≥ 65% |
| **Profit Factor** | Total ganho / Total perdido | > 1.5 |
| **Drawdown máximo** | Maior queda acumulada a partir de um pico | < 20% |
| **Sharpe Ratio** | Retorno ajustado ao risco | > 1.0 |
| **Average Win** | Ganho médio por trade vencedor | — |
| **Average Loss** | Perda média por trade perdedor | — |
| **Win/Loss Ratio** | Average Win / Average Loss | > 1.0 |

---

## Interpretação

- **Profit Factor > 1.5** → estratégia lucrativa
- **Drawdown < 20%** → risco controlado
- **Sharpe > 1** → retorno bom em relação ao risco
- **Win Rate + Profit Factor juntos** → diagnóstico completo
