# 🤖 Roboto — Bot de Trading Automatizado

Bot de trading para criptomoedas com análise técnica (RSI, MACD, EMA, Bollinger Bands) + Sentiment Analysis (FinBERT) + Risk Management + Circuit Breaker + Alertas Telegram + persistência no Supabase + dashboard web + deploy 24/7 via Docker.

[![Tests](https://img.shields.io/badge/tests-103%20passing-brightgreen)](#testes)
[![MVP](https://img.shields.io/badge/MVP-completo-brightgreen)](#roadmap)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](#setup)

---

## Arquitetura

```
roboto/
├── backend/
│   ├── market/       # BinanceClient + NewsClient (CryptoPanic + RSS fallback)
│   ├── analysis/     # TechnicalAnalyzer + SentimentAnalyzer (FinBERT) + SignalCombiner
│   ├── risk/         # RiskManager + Circuit Breaker + PerformanceMetrics
│   ├── report/       # Relatório P&L standalone (CSV + summary)
│   ├── core/         # RobotoBot (loop principal)
│   ├── api/          # FastAPI REST
│   ├── db/           # SupabaseClient
│   └── utils/        # TelegramAlert
├── frontend/
│   └── index.html    # Dashboard dark mode (servido pela API em /dashboard)
├── tests/            # Suite de testes pytest (103+ passing)
├── docker-compose.yml
├── Dockerfile
└── .env
```

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\Activate.ps1       # Windows PowerShell

pip install -r requirements.txt
cp .env.example .env             # preencha as chaves
```

> ⚠️ **NewsAPI foi removida.** Fontes de notícias são CryptoPanic (pública, sem key) + RSS fallback (CoinTelegraph, CoinDesk).

---

## Rodando

### Bot (modo terminal)
```bash
python -m backend.core.bot                          # 5 ciclos, 30s entre cada
python -m backend.core.bot --symbol ETHUSDT --interval 1m --cycles 5
python -m backend.core.bot --weak                   # aceita sinais fracos também
python -m backend.core.bot --no-db                  # desativa Supabase
python -m backend.core.bot --sleep 300 --cycles 0  # produção (infinito, 5min)
python -m backend.core.bot --max-losses 5           # circuit breaker após 5 perdas
```

### API + Dashboard
```bash
uvicorn backend.api.routes:app --reload --port 8000
```
Acesse: **http://localhost:8000/dashboard**

### Docker 24/7
```bash
cp .env.example .env      # preencha BINANCE_*, SUPABASE_*, TELEGRAM_*
docker compose up -d bot
docker compose logs -f bot
```

### Relatório P&L
```bash
python -m backend.report.pnl
```

---

## Variáveis de Ambiente (.env)

```env
# Binance
BINANCE_API_KEY=...
BINANCE_SECRET=...
BINANCE_TESTNET=true

# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=sua_anon_key

# Telegram (opcional — alertas de trade, circuit breaker, startup/shutdown)
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...

# Config do robô
DEFAULT_SYMBOL=BTCUSDT
DEFAULT_TIMEFRAME=5m
STOP_LOSS_PCT=0.05
TAKE_PROFIT_PCT=0.10
MAX_DRAWDOWN_PCT=0.20
MAX_TRADES_PER_DAY=10
MAX_CONSECUTIVE_LOSSES=3
```

> 💡 Sem `TELEGRAM_TOKEN`, o bot funciona normalmente — alertas são silenciosamente ignorados.

---

## Endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | Health check |
| GET | `/status` | Status do bot (saldo, drawdown, trade aberto) |
| GET | `/signals` | Histórico de sinais (Supabase) |
| GET | `/trades` | Trades da sessão atual |
| GET | `/trades/history` | Histórico completo de trades |
| GET | `/sessions` | Histórico de sessões |
| GET | `/metrics` | Métricas de performance |
| GET | `/candles` | Candles da Binance |
| GET | `/price` | Preço atual |
| POST | `/bot/start` | Inicia o bot em background |
| POST | `/bot/stop` | Para o bot |
| POST | `/bot/resume` | Retoma após pausa por drawdown |

---

## Supabase — Tabelas

| Tabela | Conteúdo |
|--------|----------|
| `signals` | Todos os sinais gerados a cada ciclo |
| `trades` | Trades abertos e fechados com PnL |
| `bot_sessions` | Cada execução do bot com saldo inicial/final |
| `news_cache` | Notícias processadas pelo FinBERT |
| `backtest_runs` | Resultados de backtests |

---

## Testes

Suite completa com **pytest** cobrindo todos os módulos:

```bash
# Instalar dependências de teste
pip install pytest pytest-mock

# Rodar todos os testes
python -m pytest tests/ -v --tb=short

# Ignorar testes que precisam de .env
python -m pytest tests/ -v --ignore=tests/test_api.py

# Rodar sem o smoke test (mais rápido)
python -m pytest tests/ -v --ignore=tests/test_bot_smoke.py --ignore=tests/test_api.py
```

### Cobertura atual

| Arquivo | Módulo coberto | Casos |
|---------|---------------|-------|
| `test_circuit_breaker.py` | RiskManager — N perdas pausam, reset no WIN | 6 |
| `test_news.py` | NewsClient — CryptoPanic, RSS fallback, falha silenciosa | 6 |
| `test_pnl_report.py` | PerformanceMetrics — win rate, PnL, summary, CSV | 8 |
| `test_telegram.py` | TelegramAlert — offline seguro, payload correto | 18 |
| `test_bot_smoke.py` | RobotoBot — loop completo com mocks | 7 |
| `test_risk.py` | RiskManager — drawdown, limites, trades | 12 |
| `test_signals.py` | SignalCombiner | 5 |
| `test_technical.py` | TechnicalAnalyzer | 6 |
| `test_metrics.py` | PerformanceMetrics | 8 |
| `tests/backtest/` | BacktestEngine | 10+ |

> ✅ **103+ testes passando** | ⏱ ~3 min para suite completa

---

## 📍 Roadmap

| Fase | Módulo | Status |
|------|--------|--------|
| 1 | Binance Client | ✅ Concluído |
| 2 | Análise Técnica (RSI, MACD, EMA, BB) | ✅ Concluído |
| 3 | Sentiment FinBERT | ✅ Concluído |
| 4 | Núcleo de Sinais | ✅ Concluído |
| 5 | Risk Management + Drawdown | ✅ Concluído |
| 6 | Loop Automático (`RobotoBot`) | ✅ Concluído |
| 7A | FastAPI REST | ✅ Concluído |
| 7B | Supabase — persistência de trades/sinais | ✅ Concluído |
| 7C | Dashboard web (dark mode, auto-refresh) | ✅ Concluído |
| 8 | Backtesting engine | ✅ Concluído |
| 9 | Otimização de logs e diagnóstico FinBERT | ✅ Concluído |
| 10 | **Fonte de notícias** (CryptoPanic + RSS) | ✅ Concluído (#23) |
| 11 | **Relatório P&L standalone** | ✅ Concluído (#25) |
| 12 | **Circuit Breaker N perdas** | ✅ Concluído (#24) |
| 13 | **Deploy 24/7 Docker + systemd** | ✅ Concluído (#26) |
| 14 | **Alertas Telegram** | ✅ Concluído (#27) |
| 15 | **Testes automatizados (pytest)** | ✅ Concluído (#28) |
| 16 | Modo real (Binance produção) | 🔜 A fazer |
| 17 | Deploy cloud (Render / VPS) | 🔜 A fazer |

---

## 🏁 MVP — Status (10/06/2026)

Todos os módulos do MVP estão implementados, testados e no `main`:

| Issue | Módulo | PR | Status |
|-------|--------|-----|--------|
| #18 | Fonte de notícias (CryptoPanic + RSS) | [#23](https://github.com/IsraelSiq/roboto/pull/23) | ✅ Merged |
| #19 | Relatório P&L standalone | [#25](https://github.com/IsraelSiq/roboto/pull/25) | ✅ Merged |
| #20 | Circuit breaker N perdas | [#24](https://github.com/IsraelSiq/roboto/pull/24) | ✅ Merged |
| #21 | 24/7 Docker + systemd | [#26](https://github.com/IsraelSiq/roboto/pull/26) | ✅ Merged |
| #22 | Alerta Telegram | [#27](https://github.com/IsraelSiq/roboto/pull/27) | ✅ Merged |
| — | Suite de testes MVP | [#28](https://github.com/IsraelSiq/roboto/pull/28) | 🔄 Em revisão |

### Próximos passos

1. Merge do [PR #28](https://github.com/IsraelSiq/roboto/pull/28) (testes MVP)
2. Configurar `.env` de produção com chaves reais
3. Subir via Docker:
   ```bash
   docker compose up -d bot
   ```
4. Validar primeiro alerta no Telegram
5. Acompanhar logs por 24h antes de habilitar modo real
