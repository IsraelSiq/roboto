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

> ⚠️ **NewsAPI foi removida.** O sentiment agora usa [cryptocurrency.cv](https://cryptocurrency.cv) — gratuito, sem API key, funciona em servidor.

## Rodando

### Bot direto (modo terminal)
```bash
python -m backend.core.bot                          # 5 ciclos, 30s entre cada (modo teste)
python -m backend.core.bot --symbol ETHUSDT --interval 1m --cycles 5
python -m backend.core.bot --weak                   # aceita sinais fracos também
python -m backend.core.bot --no-db                  # desativa persistência no Supabase
python -m backend.core.bot --sleep 300 --cycles 0  # modo produção (ciclos infinitos, 5min)
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

> 💡 `NEWSAPI_KEY` não é mais necessário.

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
| `backtest_runs` | Resultados de backtests |

---

## 📍 Roadmap

| Fase | Módulo | Status |
|------|--------|--------|
| 1 | Binance Client | ✅ Concluído |
| 2 | Análise Técnica (RSI, MACD, EMA, BB) | ✅ Concluído |
| 3 | Sentiment FinBERT | ✅ Concluído |
| 4 | Núcleo de Sinais | ✅ Concluído |
| 5 | Risk Management | ✅ Concluído |
| 6 | Loop Automático (`RobotoBot`) | ✅ Concluído |
| 7A | FastAPI REST | ✅ Concluído |
| 7B | Supabase — persistência de trades/sinais | ✅ Concluído |
| 7C | Dashboard web (dark mode, auto-refresh) | ✅ Concluído |
| 8 | Backtesting engine | ✅ Concluído (PR #13 pendente merge) |
| 9 | Otimização de logs e diagnóstico FinBERT | ✅ Concluído (PR #11 pendente merge) |
| 10 | Testes automatizados (pytest) | 🔄 Em andamento |
| 11 | Modo real (Binance produção) | 🔜 A fazer |
| 12 | Deploy (Render + Supabase + Vercel) | 🔜 A fazer |

---

## 💾 Ponto de Parada — 09/06/2026

### O que foi feito nesta sessão

#### PRs abertos (aguardando merge)
| PR | Branch | Descrição |
|----|--------|----------|
| [#11](https://github.com/IsraelSiq/roboto/pull/11) | `fix/issue-9-5-signal-combiner-log-e-finbert` | Logs detalhados no SignalCombiner + diagnóstico FinBERT |
| [#12](https://github.com/IsraelSiq/roboto/pull/12) | `fix/issue-6-put-backtest-engine` | Correção PUT no backtest engine |
| [#13](https://github.com/IsraelSiq/roboto/pull/13) | `feat/issue-7-atr-stop-loss` | ATR-based stop loss dinâmico |

> ⚠️ Os 3 PRs estão com CI (Lint + Tests) configurado. Verificar se os checks passaram antes do merge.

#### Commits diretos na `main` nesta sessão
- `chore`: default `--sleep 30s` e `--cycles 5` no bot (modo teste)
- `fix`: **MACD=NONE corrigido** — filtro de colunas do `pandas-ta-classic` estava errado (`MACD_` vs `MACDs_`)
- `fix`: **NewsAPI removida** — substituída por [cryptocurrency.cv](https://cryptocurrency.cv/api) (gratuito, sem key, funciona em servidor)
- `fix`: flake8 ignore expandido nos 3 branches de PR (`E221`, `E241`, `W291`, `W293`)

### Teste real com Binance Testnet — resultado

Bot rodou **10 ciclos** com dados reais da Binance Testnet (BTCUSDT ~$61.8k–$61.9k):

- ✅ Conexão Binance Testnet: OK
- ✅ 100 candles recebidos por ciclo: OK
- ✅ RSI calculando corretamente (entre 50–60)
- ✅ EMA50: preço ABOVE/AT corretamente
- ✅ RiskManager bloqueando sinais fracos com `only_strong=True`
- ✅ Trade aberto com `--weak`: CALL @ $61,786 | SL=$58,696 | TP=$67,964
- ⚠️ MACD=NONE todos os ciclos — **corrigido no último commit**
- ⚠️ NewsAPI `apiKeyInvalid` (restrição de servidor no plano free) — **corrigido com cryptocurrency.cv**
- ⚠️ Supabase `getaddrinfo failed` — URL inválida no `.env` local (não é bug de código)

### Próximos passos para retomar

1. `git pull` e rodar novamente:
   ```bash
   python -m backend.core.bot --no-db --weak
   ```
2. Verificar se **MACD agora mostra UP/DOWN** (não mais NONE)
3. Verificar se **sentiment busca notícias reais** via cryptocurrency.cv
4. Corrigir **URL do Supabase** no `.env` (se quiser persistência)
5. Fazer **merge dos PRs #11, #12, #13** após CI passar
6. Continuar **Fase 10 — testes automatizados (pytest)**
