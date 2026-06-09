# Estratégia de Trading — Roboto

## Visão geral

Estratégia baseada em combinação de dois módulos paralelos:
1. **Análise técnica** — indicadores de gráfico
2. **Sentiment analysis** — análise de notícias com FinBERT

---

## Indicadores técnicos

| Indicador | Parâmetro padrão | Função |
|---|---|---|
| RSI | length=14 | Sobrecomprado (>70) / Sobrevendido (<30) |
| MACD | fast=12, slow=26, signal=9 | Tendência + cruzamento |
| EMA50 | length=50 | Tendência de médio prazo |
| Bollinger Bands | length=20, std=2 | Breakout e reversão |

---

## Lógica de sinal técnico

```python
if RSI < 30 and MACD cruzou acima and price > EMA50:
    sinal_tecnico = "CALL"
elif RSI > 70 and MACD cruzou abaixo and price < EMA50:
    sinal_tecnico = "PUT"
else:
    sinal_tecnico = "AGUARDAR"
```

---

## Lógica de combinação (núcleo ⭐)

| Técnico | Sentiment | Decisão final |
|---|---|---|
| CALL | positivo | ✅ CALL FORTE |
| CALL | negativo | ⚠️ CALL FRACO / AGUARDAR |
| PUT | negativo | ✅ PUT FORTE |
| PUT | positivo | ⚠️ PUT FRACO / AGUARDAR |
| AGUARDAR | qualquer | ⏸️ AGUARDAR |

---

## Ativo e timeframe padrão

- **Ativo:** BTC/USDT
- **Timeframe:** 5 minutos
- **Exchange:** Binance (testnet primeiro)
