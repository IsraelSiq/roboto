# 🤖 Roboto — Bot de Trading BTC/USDT

[![CI](https://github.com/IsraelSiq/roboto/actions/workflows/ci.yml/badge.svg)](https://github.com/IsraelSiq/roboto/actions/workflows/ci.yml)
[![Deploy Frontend](https://github.com/IsraelSiq/roboto/actions/workflows/deploy-frontend.yml/badge.svg)](https://github.com/IsraelSiq/roboto/actions/workflows/deploy-frontend.yml)
[![Deploy Backend](https://github.com/IsraelSiq/roboto/actions/workflows/deploy-backend.yml/badge.svg)](https://github.com/IsraelSiq/roboto/actions/workflows/deploy-backend.yml)

Bot de trading automático para BTCUSDT que combina **análise técnica** (RSI, MACD, EMA, Bollinger Bands, ATR) com **análise de sentiment** (FinBERT) para gerar sinais de CALL/PUT com stop loss dinâmico e backtest integrado.

**Stack em produção:**
- 🌐 **Dashboard:** [roboto-beta.vercel.app](https://roboto-beta.vercel.app)
- ⚡ **API:** [roboto-tau3.onrender.com](https://roboto-tau3.onrender.com)
- 🧪 **Testnet:** Binance Testnet (sandbox seguro)

> ⚠️ **Nota:** O servidor Render está em região bloqueada pela Binance. Para usar em produção com dados reais, rode localmente ou configure um proxy.

---

## Arquitetura

```
frontend/                        ← servido em /dashboard/ pelo FastAPI
    index.html      — dashboard principal (sinais + trades)
    reports.html    — relatórios, equity curve, exportar CSV
    control.html    — painel de controle do bot (start/stop/config)
    backtest.html   — backtest interativo com gráfico de equity

backend/
    core/bot.py          — loop principal do bot
    analysis/
        technical.py     — RSI, MACD, EMA50, BB, ATR
        sentiment.py     — FinBERT (ProsusAI/finbert)
    market/
        binance_client.py    — Binance REST (testnet/real)
        news_client.py       — CryptoPanic + RSS
    risk/
        manager.py       — stop loss ATR, take profit, drawdown
        metrics.py       — win rate, sharpe, profit factor
    api/
        routes.py            — FastAPI — monta todos os routers + StaticFiles
        health.py            — /metrics/health
        backtest_router.py   — POST /backtest/run, GET /backtest/history
    db/
        supabase_client.py
    utils/
        telegram.py      — alertas Telegram

scripts/
    smoke_test.py    — testa todos os endpoints locais ou em produção

docs/
    sandbox.md       — Binance Testnet setup
    deploy.md        — Vercel + Render deploy
```

---

## Setup rápido

```bash
git clone https://github.com/IsraelSiq/roboto
cd roboto
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
cp .env.example .env         # preencha as variáveis
uvicorn backend.api.routes:app --reload --port 8000
```

Guias detalhados:
- [`docs/sandbox.md`](docs/sandbox.md) — Binance Testnet setup
- [`docs/deploy.md`](docs/deploy.md) — Vercel + Render deploy

---

## Dashboard

Após subir a API, acesse pelo browser:

| Página | URL local | Descrição |
|---|---|---|
| Dashboard | http://localhost:8000/dashboard/ | Sinais em tempo real + trades |
| Relatórios | http://localhost:8000/dashboard/reports.html | Equity curve, win rate, exportar CSV |
| Controle | http://localhost:8000/dashboard/control.html | Start/stop/config do bot |
| Backtest | http://localhost:8000/dashboard/backtest.html | Simulação histórica interativa |
| Swagger | http://localhost:8000/docs | Documentação interativa da API |

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

## Endpoints da API

### Públicos

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/health` | Liveness probe |
| GET | `/metrics/health` | Status detalhado (Binance/Supabase/FinBERT) |
| GET | `/status` | Status do bot |
| GET | `/price` | Preço atual do BTC |
| GET | `/signals` | Últimos sinais gerados |
| GET | `/trades/history` | Histórico de trades |
| GET | `/reports/summary` | Resumo de performance |
| GET | `/reports/equity-curve` | Equity curve |
| GET | `/reports/trades` | Trades paginados com filtros |
| GET | `/reports/export/csv` | Exportar trades CSV |
| GET | `/backtest/history` | Histórico de backtests salvos |

### Autenticados (Bearer token)

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/bot/start` | Iniciar bot |
| POST | `/bot/stop` | Parar bot |
| POST | `/bot/resume` | Retomar bot pausado |
| POST | `/backtest/run` | Rodar backtest |

---

## Backtest

O backtest simula a estratégia candle a candle usando dados históricos reais da Binance.

**Parâmetros disponíveis:**

| Parâmetro | Descrição | Padrão |
|---|---|---|
| `symbol` | Par de trading | `BTCUSDT` |
| `interval` | Timeframe (1m, 5m, 15m, 1h...) | `5m` |
| `start` | Data inicial (YYYY-MM-DD) | `2026-01-01` |
| `end` | Data final (opcional) | hoje |
| `balance` | Saldo inicial em USDT | `10000` |
| `only_strong` | Só sinais fortes (CALL_FORTE/PUT_FORTE) | `true` |
| `use_atr_stop` | Stop loss dinâmico por ATR | `false` |
| `atr_multiplier` | Multiplicador ATR para SL | `1.5` |
| `rr_ratio` | Risk:Reward ratio | `2.0` |
| `macro_filter_enabled` | Filtro de tendência macro | `false` |
| `save` | Salvar resultado no Supabase | `true` |

**Métricas retornadas:** win rate, sharpe ratio, max drawdown, profit factor, PnL total, equity curve, lista de trades simulados, veredicto APROVADO/REPROVADO.

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
| #2  | Backtest integrado (router + UI) | ✅ |
