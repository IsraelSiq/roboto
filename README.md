# 🤖 Roboto — Bot de Trading BTC/USDT

[![CI](https://github.com/IsraelSiq/roboto/actions/workflows/ci.yml/badge.svg)](https://github.com/IsraelSiq/roboto/actions/workflows/ci.yml)
[![Deploy Frontend](https://github.com/IsraelSiq/roboto/actions/workflows/deploy-frontend.yml/badge.svg)](https://github.com/IsraelSiq/roboto/actions/workflows/deploy-frontend.yml)
[![Deploy Backend](https://github.com/IsraelSiq/roboto/actions/workflows/deploy-backend.yml/badge.svg)](https://github.com/IsraelSiq/roboto/actions/workflows/deploy-backend.yml)

Bot de trading automático para BTCUSDT que combina **análise técnica** (RSI, MACD, EMA, Bollinger Bands) com **análise de sentiment** (FinBERT) para gerar sinais de CALL/PUT.

**Stack em produção:**
- 🌐 **Dashboard:** [roboto-beta.vercel.app](https://roboto-beta.vercel.app)
- ⚡ **API:** [roboto-tau3.onrender.com](https://roboto-tau3.onrender.com)
- 🧪 **Testnet:** Binance Testnet (sandbox seguro)

---

## Arquitetura

```
frontend/ (Vercel — HTML estático)
    index.html      — dashboard principal
    reports.html    — relatórios e equity curve

backend/
    core/bot.py     — loop principal do bot
    analysis/
        technical.py  — RSI, MACD, EMA50, BB, ATR
        sentiment.py  — FinBERT (ProsusAI/finbert)
    market/
        binance_client.py  — Binance REST (testnet/real)
        news_client.py     — CryptoPanic + RSS
    risk/
        manager.py    — stop loss ATR, take profit, drawdown
        metrics.py    — win rate, sharpe, profit factor
    api/
        routes.py     — FastAPI REST
        health.py     — /metrics/health (#31)
    db/
        supabase_client.py
    utils/
        telegram.py   — alertas Telegram
```

---

## Setup rápido

```bash
git clone https://github.com/IsraelSiq/roboto
cd roboto
pip install -r requirements.txt
cp .env.example .env   # preencha as variáveis
python scripts/smoke_test.py
```

Guias detalhados:
- [`docs/sandbox.md`](docs/sandbox.md) — Binance Testnet setup
- [`docs/deploy.md`](docs/deploy.md) — Vercel + Render deploy

---

## Variáveis de ambiente

| Variável | Descrição | Obrigatória |
|---|---|---|
| `BINANCE_API_KEY` | API Key Binance | ✅ |
| `BINANCE_SECRET` | Secret Key Binance | ✅ |
| `BINANCE_TESTNET` | `true` para sandbox | ✅ |
| `SUPABASE_URL` | URL do projeto Supabase | ✅ |
| `SUPABASE_KEY` | Service role key | ✅ |
| `NEWSAPI_KEY` | NewsAPI key | ✅ |
| `API_TOKEN` | Bearer token para /bot/* | recomendado |
| `ALLOWED_ORIGINS` | CORS origins (CSV) | recomendado |
| `TELEGRAM_TOKEN` | Token do bot Telegram | opcional |
| `TELEGRAM_CHAT_ID` | Chat ID do Telegram | opcional |
| `DRAWDOWN_ALERT_PCT` | Threshold drawdown alerta (padrão: 10) | opcional |
| `WARMUP_ON_STARTUP` | Pré-aquece FinBERT no startup | opcional |
| `LOG_FORMAT` | `json` para log estruturado | opcional |
| `WEB_CONCURRENCY` | Workers uvicorn (padrão: 1) | opcional |

---

## Endpoints principais

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/health` | Liveness probe |
| GET | `/metrics/health` | Status detalhado (Binance/Supabase/FinBERT) |
| GET | `/status` | Status do bot |
| GET | `/signals` | Últimos sinais |
| GET | `/trades/history` | Histórico de trades |
| GET | `/reports/summary` | Resumo de performance |
| GET | `/reports/equity-curve` | Equity curve |
| GET | `/reports/export/csv` | Exportar trades CSV |
| POST | `/bot/start` | Iniciar bot |
| POST | `/bot/stop` | Parar bot |

---

## Smoke Test

```bash
# Local
python scripts/smoke_test.py

# Contra produção
python scripts/smoke_test.py --api-url https://roboto-tau3.onrender.com
```

---

## Issues resolvidas

| Issue | Título | Status |
|---|---|---|
| #14 | Warmup FinBERT lazy loading | ✅ |
| #15 | Cache Supabase de notícias | ✅ |
| #16 | Stop loss dinâmico ATR | ✅ |
| #29 | Página de relatórios | ✅ |
| #30 | Deploy Vercel + CI/CD | ✅ |
| #31 | Monitoramento e alertas | ✅ |
