# 🤖 Roboto

> Robô de trading com análise técnica + sentiment analysis na Binance.  
> Estudo e validação antes de qualquer capital real.

---

## ⚠️ Aviso Legal

Este projeto é **exclusivamente para fins de estudo**.  
Não é recomendação financeira. Criptomoedas envolvem alto risco de perda.  
**Nunca coloque dinheiro real sem backtest sólido e entendimento completo dos riscos.**

---

## 🎯 Objetivo

Construir um robô de trading que:
- Combina **análise técnica** (RSI, MACD, EMA, Bollinger Bands) com **sentiment analysis** de notícias (FinBERT)
- Opera na **Binance** (testnet primeiro, real depois)
- Só avança para capital real após atingir **≥ 65% de win rate** em backtest + alpha test
- Tem **risk management** embutido: stop loss, take profit, max trades/dia

---

## 🏗️ Arquitetura

```
roboto/
├── backend/
│   ├── config.py                  # Variáveis de ambiente + validação
│   ├── main.py                    # FastAPI — 8 rotas
│   ├── market/
│   │   ├── binance_client.py      # Conexão Binance (testnet/real)
│   │   ├── data_collector.py      # 2 threads paralelas: candles + notícias
│   │   └── symbols.py             # Lista de ativos recomendados para day trading
│   ├── analysis/
│   │   ├── technical.py           # RSI + MACD + EMA50 + Bollinger Bands
│   │   ├── sentiment.py           # FinBERT + NewsAPI
│   │   └── signals.py             # ⭐ Combinação técnico + sentiment (NÚCLEO)
│   ├── risk/
│   │   ├── manager.py             # Stop loss, take profit, max trades/dia
│   │   └── metrics.py             # Win rate, profit factor, drawdown, Sharpe
│   ├── strategies/
│   │   └── simple_rsi_macd.py    # Orquestrador do ciclo principal
│   └── utils/
│       └── logging.py             # Log de sinais no Supabase
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── SignalCard.tsx      # Sinal atual (CALL/PUT/AGUARDAR + força)
│       │   ├── SentimentPanel.tsx # Notícias + scores FinBERT
│       │   ├── MetricsChart.tsx   # Win Rate, Profit Factor, Drawdown
│       │   └── HistoryTable.tsx   # Histórico de sinais do Supabase
│       └── services/
│           └── api.ts             # Chamadas ao backend
├── tests/
│   └── backtest/
│       └── run_backtest.py        # Backtest histórico de 3 meses
├── alpha_test.py                  # 🧪 Ponto de teste alpha (paper trading local)
├── docs/
│   ├── supabase_schema.sql        # Schema das tabelas signals + trades
│   ├── VALIDACAO.md               # Metodologia de validação por fase
│   ├── METRICAS.md                # Definição das métricas usadas
│   └── ESTRATEGIA.md              # Documentação da estratégia
├── .env.example
├── requirements.txt
├── .gitignore
└── docker-compose.yml
```

---

## 🧠 Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11 + FastAPI |
| Análise técnica | pandas-ta (130+ indicadores) |
| Sentiment | FinBERT (HuggingFace) + NewsAPI |
| Conexão Binance | python-binance (API oficial) |
| Banco de dados | Supabase (PostgreSQL) |
| Frontend | Next.js + TailwindCSS + Recharts |
| Deploy backend | Railway |
| Deploy frontend | Vercel |
| Ambiente de testes | Binance Testnet |

---

## 🔑 Ativos Recomendados para Day Trading

| Ativo | Por quê |
|---|---|
| **BTC/USDT** | Mais líquido, menos manipulação, movimentos consistentes |
| **ETH/USDT** | Segunda maior, boa volatilidade |
| **BNB/USDT** | Boa liquidez, volatilidade média |
| **SOL/USDT** | Alta volatilidade, bom para day trading agressivo |

> Padrão inicial: **BTC/USDT** no timeframe de **5 minutos**.

---

## ⭐ Lógica de Combinação de Sinais (NÚCLEO)

| Técnico | Sentiment | Decisão |
|---|---|---|
| CALL | positivo | ✅ CALL FORTE |
| CALL | negativo | ⚠️ CALL FRACO / AGUARDAR |
| PUT | negativo | ✅ PUT FORTE |
| PUT | positivo | ⚠️ PUT FRACO / AGUARDAR |
| AGUARDAR | qualquer | ⏸️ AGUARDAR |

---

## 🛡️ Risk Management

| Proteção | Valor padrão |
|---|---|
| Stop loss por trade | 5% |
| Take profit por trade | 10% |
| Max trades por dia | 10 |
| Sem trades em notícias grandes | FOMC, CPI, hacks |
| Drawdown máximo | 20% |

---

## 📊 Métricas de Avaliação

| Métrica | Meta |
|---|---|
| Win rate | ≥ 65% |
| Profit factor | > 1.5 |
| Drawdown máximo | < 20% |
| Sharpe ratio | > 1 |

---

## 🚦 Fases do Projeto

| Fase | Objetivo | Tempo estimado |
|---|---|---|
| Fase 0 | Setup inicial + estrutura | 1 dia |
| Fase 1 | Conexão Binance + coleta de dados | 2 dias |
| Fase 2 | Análise técnica (pandas-ta) | 2 dias |
| Fase 3 | Sentiment analysis (FinBERT + NewsAPI) | 3 dias |
| Fase 4 | Combinação técnico + sentiment ⭐ | 2 dias |
| Fase 5 | Risk management + métricas | 2 dias |
| Fase 6 | Estratégia principal + ciclo automático | 2 dias |
| Fase 7 | Backtest histórico (3 meses) | 3 dias |
| Fase 8 | Alpha test local (paper trading) 🧪 | 3–5 dias |
| Fase 9 | Testnet Binance (dinheiro virtual real) | 2 semanas |
| Fase 10 | Dashboard frontend | 3 dias |
| Fase 11 | Capital real pequeno ($10–$20) | Após Fase 9 aprovada |

---

## ✅ 47 Tasks — Checklist Completo

### 🟦 Fase 0 — Setup do repositório (4 tasks)

- [ ] **0.1** — Criar repositório `roboto` no GitHub + estrutura de pastas  
  `feat: setup inicial com estrutura de pastas`
- [ ] **0.2** — Adicionar `requirements.txt` e `.gitignore`  
  `feat: adicionar requirements.txt e .gitignore`
- [ ] **0.3** — Criar `backend/config.py` com variáveis de ambiente (`.env`)  
  `feat: adicionar config.py com variáveis de ambiente`
- [ ] **0.4** — Criar `README.md` completo  
  `docs: criar README.md completo`

---

### 🟦 Fase 1 — Conexão Binance + coleta de dados (5 tasks)

- [ ] **1.1** — Criar conta Binance Testnet em https://testnet.binance.vision + gerar API Key/Secret  
  `feat: configurar credenciais Binance testnet`
- [ ] **1.2** — Implementar `binance_client.py` com conexão testnet  
  `feat: implementar binance_client.py com conexão testnet`
- [ ] **1.3** — Implementar `get_candles()` e `get_historical_candles()` para backtest  
  `feat: implementar get_candles para obter candles BTCUSDT`
- [ ] **1.4** — Implementar `data_collector.py` com 2 threads paralelas (candles + notícias)  
  `feat: implementar data_collector.py com threads paralelas`
- [ ] **1.5** — Criar `symbols.py` com lista de ativos recomendados  
  `feat: adicionar symbols.py com lista de ativos ideais`

---

### 🟦 Fase 2 — Análise técnica (4 tasks)

- [ ] **2.1** — Implementar `technical.py` com RSI + EMA50  
  `feat: implementar technical.py com RSI e EMA50`
- [ ] **2.2** — Adicionar MACD com detecção de cruzamento  
  `feat: adicionar MACD com detecção de cruzamento`
- [ ] **2.3** — Adicionar Bollinger Bands  
  `feat: adicionar Bollinger Bands em technical.py`
- [ ] **2.4** — Implementar lógica de sinal técnico CALL/PUT/AGUARDAR  
  `feat: implementar lógica de sinal técnico`

---

### 🟦 Fase 3 — Sentiment Analysis ⭐ (5 tasks)

- [ ] **3.1** — Criar conta NewsAPI em https://newsapi.org + adicionar key no `.env`  
  `feat: configurar NewsAPI key`
- [ ] **3.2** — Implementar `sentiment.py` com pipeline FinBERT (download ~440MB)  
  `feat: implementar sentiment.py com FinBERT`
- [ ] **3.3** — Integrar NewsAPI para buscar notícias do ativo automaticamente  
  `feat: integrar NewsAPI em data_collector.py`
- [ ] **3.4** — Implementar classificação positive/negative/neutral com score de confiança  
  `feat: classificação sentiment com score de confiança`
- [ ] **3.5** — Adicionar cache de notícias para evitar chamadas duplicadas  
  `feat: adicionar cache de notícias no data_collector`

---

### 🟦 Fase 4 — Combinação de sinais ⭐ NÚCLEO (5 tasks)

- [ ] **4.1** — Criar `signals.py` com função `combine(technical, sentiment)`  
  `feat: criar signals.py com função combine`
- [ ] **4.2** — Implementar tabela de decisão (CALL FORTE / PUT FORTE / AGUARDAR)  
  `feat: implementar tabela de decisão combinada`
- [ ] **4.3** — Testar cenário de conflito (CALL técnico + negative sentiment → AGUARDAR)  
  `test: validar cenário de conflito de sinais`
- [ ] **4.4** — Adicionar campo `reason` explicando a decisão final  
  `feat: adicionar campo reason na decisão final`
- [ ] **4.5** — Testar combinação isolada com TechnicalSignal + SentimentSignal mocados  
  `test: testar combinação de sinais com dados mockados`

---

### 🟦 Fase 5 — Risk Management (4 tasks)

- [ ] **5.1** — Implementar `risk/manager.py` com stop loss, take profit e max trades/dia  
  `feat: implementar risk manager com stop loss e take profit`
- [ ] **5.2** — Implementar `risk/metrics.py` com win rate, profit factor, drawdown, Sharpe  
  `feat: implementar métricas de performance`
- [ ] **5.3** — Adicionar lógica de pausa automática quando drawdown > 20%  
  `feat: adicionar pausa automática por drawdown`
- [ ] **5.4** — Testar risk manager e métricas com trades simulados  
  `test: validar risk manager com trades simulados`

---

### 🟦 Fase 6 — Estratégia principal + ciclo automático (3 tasks)

- [ ] **6.1** — Implementar `strategies/simple_rsi_macd.py` orquestrando ciclo completo  
  `feat: estratégia principal RSI+MACD orquestrando ciclo completo`
- [ ] **6.2** — Criar `backend/main.py` com FastAPI e 8 rotas (`/`, `/signal`, `/metrics`, `/risk`, `/data`, `/news`, `/candles`, `/risk/pause`)  
  `feat: adicionar entry point FastAPI com 8 rotas`
- [ ] **6.3** — Testar ciclo completo local: rodar API + confirmar `/signal` retornando sinal com técnico + sentiment  
  `test: validar ciclo completo via FastAPI`

---

### 🟦 Fase 7 — Backtest histórico (4 tasks)

- [ ] **7.1** — Implementar `tests/backtest/run_backtest.py` com 3 meses de candles históricos  
  `feat: backtest histórico com 3 meses de candles`
- [ ] **7.2** — Rodar backtest e registrar resultado em `docs/VALIDACAO.md`  
  `docs: registrar resultado do backtest em VALIDACAO.md`
- [ ] **7.3** — Meta: win rate ≥ 65%. Se não atingir → ajustar parâmetros RSI/MACD e repetir  
  `fix: ajustar parâmetros de estratégia conforme backtest`
- [ ] **7.4** — Criar `docs/ESTRATEGIA.md` documentando indicadores e lógica final  
  `docs: documentar estratégia final em ESTRATEGIA.md`

---

### 🟦 Fase 8 — Alpha Test local 🧪 (3 tasks) — PONTO DE VALIDAÇÃO

- [ ] **8.1** — Rodar alpha test de 10 ciclos rápidos para verificar sem erros:  
  `python alpha_test.py --cycles 10 --interval 30`  
  `feat: script de alpha test local com paper trading`
- [ ] **8.2** — Rodar alpha test completo: 50 ciclos, intervalo de 5min (real):  
  `python alpha_test.py --cycles 50 --interval 300 --symbol BTCUSDT`  
  `test: alpha test completo 50 ciclos BTCUSDT`
- [ ] **8.3** — Meta: win rate ≥ 65% → ✅ avançar para Testnet. Se não → ajustar e repetir  
  `docs: registrar resultado alpha test`

---

### 🟦 Fase 9 — Testnet Binance (3 tasks)

- [ ] **9.1** — Confirmar `BINANCE_TESTNET=true` no `.env` e ativar execução real de ordens no `simple_rsi_macd.py`  
  `feat: ativar execução de ordens no testnet`
- [ ] **9.2** — Rodar robô por 1–2 semanas monitorando `GET /metrics` diariamente  
  `test: monitoramento testnet por 2 semanas`
- [ ] **9.3** — Meta: win rate ≥ 62% em ≥ 30 trades → registrar em `docs/VALIDACAO.md`  
  `docs: registrar resultado testnet`

---

### 🟦 Fase 10 — Dashboard Frontend (7 tasks)

- [ ] **10.1** — Setup Next.js com Tailwind + Recharts:  
  `cd frontend && npx create-next-app@latest . --typescript --tailwind --app && npm install recharts lucide-react`  
  `feat: setup Next.js com Tailwind e Recharts`
- [ ] **10.2** — Implementar `SignalCard` — sinal atual (CALL/PUT/AGUARDAR + força + reason)  
  `feat: implementar SignalCard com sinal atual`
- [ ] **10.3** — Implementar `SentimentPanel` — notícias com scores FinBERT  
  `feat: implementar SentimentPanel com scores`
- [ ] **10.4** — Implementar `MetricsChart` — Win Rate, Profit Factor, Drawdown em gráfico  
  `feat: implementar MetricsChart com Recharts`
- [ ] **10.5** — Implementar `HistoryTable` — histórico de sinais do Supabase  
  `feat: implementar HistoryTable com dados Supabase`
- [ ] **10.6** — Conectar frontend ao backend via `GET /signal`, `GET /metrics`, `GET /news`  
  `feat: conectar frontend ao backend via API`
- [ ] **10.7** — Deploy frontend no Vercel + backend no Railway  
  `chore: deploy frontend Vercel + backend Railway`

---

## 🗓️ Ordem de Execução Recomendada

```
HOJE
├── Fase 0 → criar repo + subir arquivos no GitHub
├── Fase 1 → criar contas Binance testnet + NewsAPI + Supabase
└── Fase 2 → testar análise técnica isolada

AMANHÃ
├── Fase 3 → testar FinBERT + NewsAPI
├── Fase 4 → testar combinação de sinais
└── Fase 5 → testar risk manager + métricas

ESSA SEMANA
├── Fase 6 → rodar API completa local
├── Fase 7 → rodar backtest 3 meses
└── Fase 8 → 🧪 ALPHA TEST ← meta desta semana

PRÓXIMAS 2 SEMANAS
├── Fase 9 → testnet Binance
└── Fase 10 → dashboard frontend

SÓ APÓS FASE 9 APROVADA
└── Capital real (mínimo $10–$20)
```

---

## 🚀 Como instalar e rodar

```bash
# 1. Clonar o repositório
git clone https://github.com/IsraelSiq/roboto.git
cd roboto

# 2. Criar e preencher o .env
cp .env.example .env
# Editar .env com suas keys (Binance testnet, NewsAPI, Supabase)

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Criar tabelas no Supabase
# Rodar docs/supabase_schema.sql no SQL Editor do Supabase

# 5. Rodar a API
uvicorn backend.main:app --reload --port 8000
# Acesse http://localhost:8000/signal
```

---

## 📡 Rotas da API

| Rota | O que retorna |
|---|---|
| `GET /` | Status do bot (online/offline) |
| `GET /signal` | Sinal atual completo (técnico + sentiment + decisão) |
| `GET /metrics` | Win rate, profit factor, drawdown, Sharpe |
| `GET /risk` | Status do risk manager |
| `GET /data` | Snapshot dos dados coletados |
| `GET /news` | Últimas notícias coletadas |
| `GET /candles` | Últimos 20 candles |
| `POST /risk/pause` | Pausar o bot |
| `POST /risk/resume` | Retomar o bot |

---

## 🎯 Critério de Aprovação por Fase

| Fase | Ferramenta | Meta |
|---|---|---|
| Alpha local | `alpha_test.py` | Win rate ≥ 65% |
| Backtest | `run_backtest.py` | Win rate ≥ 65% |
| Testnet Binance | API real (testnet) | Win rate ≥ 62% |
| Capital real | Binance real | Só após as 3 acima ✅ |

---

*Desenvolvido por [Israel Siqueira](https://github.com/IsraelSiq) — projeto de estudo.*
