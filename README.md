# 🤖 Roboto — Bot de Trading Automatizado

Bot de trading para criptomoedas com análise técnica (RSI, MACD, EMA, Bollinger Bands) + Sentiment Analysis (FinBERT) + Risk Management + persistência no Supabase + dashboard web.

## Arquitetura

```
roboto/
├── backend/
│   ├── market/       # BinanceClient (candles, preço)
│   ├── analysis/     # TechnicalAnalyzer + SentimentAnalyzer (FinBERT) + SignalCombiner
│   ├── risk/         # RiskManager + PerformanceMetrics
│   ├── core/         # RobotoBot (loop principal)
│   ├── api/          # FastAPI REST
│   └── db/           # SupabaseClient
├── frontend/
│   └── index.html    # Dashboard dark mode (servido pela API em /dashboard)
└── .env
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # preencha as chaves
```

## Rodando

### Bot direto (modo terminal)
```bash
python -m backend.core.bot
python -m backend.core.bot --symbol ETHUSDT --interval 1m --cycles 5
python -m backend.core.bot --weak        # aceita sinais fracos também
python -m backend.core.bot --no-db       # desativa persistência no Supabase
```

### API + Dashboard
```bash
python -m backend.api.routes
# ou
uvicorn backend.api.routes:app --reload --port 8000
```

Depois acesse: **http://localhost:8000/dashboard**

## Variáveis de Ambiente (.env)

```env
# Binance
BINANCE_API_KEY=...
BINANCE_SECRET=...
BINANCE_TESTNET=true        # true = testnet | false = conta real

# NewsAPI
NEWSAPI_KEY=...

# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=sua_anon_key

# Config do robô
DEFAULT_SYMBOL=BTCUSDT
DEFAULT_TIMEFRAME=5m
STOP_LOSS_PCT=0.05
TAKE_PROFIT_PCT=0.10
MAX_DRAWDOWN_PCT=0.20
MAX_TRADES_PER_DAY=10
```

## Endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | Health check |
| GET | `/status` | Status do bot (saldo, drawdown, trade aberto) |
| GET | `/signals` | Histórico de sinais (Supabase) |
| GET | `/trades` | Trades da sessão atual |
| GET | `/trades/history` | Histórico completo de trades (Supabase) |
| GET | `/sessions` | Histórico de sessões (Supabase) |
| GET | `/metrics` | Métricas de performance |
| GET | `/candles` | Candles da Binance |
| GET | `/price` | Preço atual |
| POST | `/bot/start` | Inicia o bot em background |
| POST | `/bot/stop` | Para o bot |
| POST | `/bot/resume` | Retoma após pausa por drawdown |

## Supabase — Tabelas

| Tabela | Conteúdo |
|--------|----------|
| `signals` | Todos os sinais gerados a cada ciclo |
| `trades` | Trades abertos e fechados com PnL |
| `bot_sessions` | Cada execução do bot com saldo inicial/final |
| `news_cache` | Notícias processadas pelo FinBERT |
| `backtest_runs` | Resultados de backtests (Fase 8) |

## Roadmap

| Fase | Módulo | Status |
|------|--------|---------|
| 1 | Binance Client | ✅ |
| 2 | Análise Técnica (RSI, MACD, EMA, BB) | ✅ |
| 3 | Sentiment FinBERT | ✅ |
| 4 | Núcleo de Sinais | ✅ |
| 5 | Risk Management | ✅ |
| 6 | Loop Automático | ✅ |
| 7A | FastAPI REST | ✅ |
| 7B | Supabase — persistência de trades/sinais | ✅ |
| 7C | Dashboard web (dark mode, auto-refresh) | ✅ |
| 8 | Backtesting | 🔜 |
| 9 | Otimização de estratégia | 🔜 |
| 10 | Testes automatizados (pytest) | 🔜 |
| 11 | Modo real (Binance produção) | 🔜 |
| 12 | Deploy (Render + Supabase + Vercel) | 🔜 |
