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
│       ├── lib/
│       │   ├── supabase.ts        # Cliente Supabase + tipos TypeScript
│       │   └── api.ts             # Chamadas ao backend
│       └── components/
│           ├── SignalCard.tsx      # Sinal atual (CALL/PUT/AGUARDAR + força)
│           ├── SentimentPanel.tsx # Notícias + scores FinBERT
│           ├── MetricsChart.tsx   # Win Rate, Profit Factor, Drawdown
│           └── HistoryTable.tsx   # Histórico de sinais do Supabase
├── tests/
│   └── backtest/
│       └── run_backtest.py        # Backtest histórico de 3 meses
├── alpha_test.py                  # 🧪 Ponto de teste alpha (paper trading local)
├── docs/
│   ├── supabase_schema.sql        # Schema das tabelas (4 tabelas + RLS)
│   ├── INFRA.md                   # Arquitetura GitHub + Vercel + Supabase
│   ├── VALIDACAO.md               # Metodologia de validação por fase
│   ├── METRICAS.md                # Definição das métricas usadas
│   └── ESTRATEGIA.md              # Documentação da estratégia
├── .github/
│   └── workflows/
│       └── ci.yml                 # GitHub Actions: testes automáticos em todo PR
├── .env.example
├── requirements.txt
├── .gitignore
├── Dockerfile
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
| Banco de dados | Supabase (PostgreSQL + Realtime) |
| Frontend | Next.js + TailwindCSS + Recharts |
| Deploy frontend | Vercel (automático a cada push) |
| Deploy backend | Railway |
| Ambiente de testes | Binance Testnet |
| CI/CD | GitHub Actions |

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

| Fase | Objetivo | Tempo estimado | Status |
|---|---|---|---|
| Fase 0 | Setup inicial + estrutura | 1 dia | ✅ Concluída |
| Fase 1 | Conexão Binance + coleta de dados | 2 dias | 🔄 Em andamento |
| Fase 2 | Análise técnica (pandas-ta) | 2 dias | ⏳ Pendente |
| Fase 3 | Sentiment analysis (FinBERT + NewsAPI) | 3 dias | ⏳ Pendente |
| Fase 4 | Combinação técnico + sentiment ⭐ | 2 dias | ⏳ Pendente |
| Fase 5 | Risk management + métricas | 2 dias | ⏳ Pendente |
| Fase 6 | Estratégia principal + ciclo automático | 2 dias | ⏳ Pendente |
| Fase 7 | Backtest histórico (3 meses) | 3 dias | ⏳ Pendente |
| Fase 8 | Alpha test local (paper trading) 🧪 | 3–5 dias | ⏳ Pendente |
| Fase 9 | Testnet Binance (dinheiro virtual real) | 2 semanas | ⏳ Pendente |
| Fase 10 | Dashboard frontend | 3 dias | ⏳ Pendente |
| Fase 11 | Capital real pequeno ($10–$20) | Após Fase 9 aprovada | 🔒 Bloqueado |

---

## ✅ 47 Tasks — Checklist Completo

### ✅ ~~Fase 0 — Setup do repositório~~ (4/4 concluídas)

- [x] **0.1** — Criar repositório `roboto` no GitHub + estrutura de pastas
- [x] **0.2** — Adicionar `requirements.txt` e `.gitignore`
- [x] **0.3** — Criar `backend/config.py` com variáveis de ambiente (`.env`)
- [x] **0.4** — Criar `README.md` completo + `docs/INFRA.md` com arquitetura GitHub + Vercel + Supabase

---

### 🔄 Fase 1 — Conexão Binance + coleta de dados (0/5 concluídas)

- [x] **1.1** — Criar conta Binance Testnet em https://testnet.binance.vision + gerar API Key (Ed25519)  
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

### 🟦 Fase 2 — Análise técnica (0/4 concluídas)

- [ ] **2.1** — Implementar `technical.py` com RSI + EMA50  
  `feat: implementar technical.py com RSI e EMA50`
- [ ] **2.2** — Adicionar MACD com detecção de cruzamento  
  `feat: adicionar MACD com detecção de cruzamento`
- [ ] **2.3** — Adicionar Bollinger Bands  
  `feat: adicionar Bollinger Bands em technical.py`
- [ ] **2.4** — Implementar lógica de sinal técnico CALL/PUT/AGUARDAR  
  `feat: implementar lógica de sinal técnico`

---

### 🟦 Fase 3 — Sentiment Analysis ⭐ (0/5 concluídas)

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

### 🟦 Fase 4 — Combinação de sinais ⭐ NÚCLEO (0/5 concluídas)

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

### 🟦 Fase 5 — Risk Management (0/4 concluídas)

- [ ] **5.1** — Implementar `risk/manager.py` com stop loss, take profit e max trades/dia  
  `feat: implementar risk manager com stop loss e take profit`
- [ ] **5.2** — Implementar `risk/metrics.py` com win rate, profit factor, drawdown, Sharpe  
  `feat: implementar métricas de performance`
- [ ] **5.3** — Adicionar lógica de pausa automática quando drawdown > 20%  
  `feat: adicionar pausa automática por drawdown`
- [ ] **5.4** — Testar risk manager e métricas com trades simulados  
  `test: validar risk manager com trades simulados`

---

### 🟦 Fase 6 — Estratégia principal + ciclo automático (0/3 concluídas)

- [ ] **6.1** — Implementar `strategies/simple_rsi_macd.py` orquestrando ciclo completo  
  `feat: estratégia principal RSI+MACD orquestrando ciclo completo`
- [ ] **6.2** — Criar `backend/main.py` com FastAPI e 9 rotas  
  `feat: adicionar entry point FastAPI com 9 rotas`
- [ ] **6.3** — Testar ciclo completo local: rodar API + confirmar `/signal` retornando sinal completo  
  `test: validar ciclo completo via FastAPI`

---

### 🟦 Fase 7 — Backtest histórico (0/4 concluídas)

- [ ] **7.1** — Implementar `tests/backtest/run_backtest.py` com 3 meses de candles históricos  
  `feat: backtest histórico com 3 meses de candles`
- [ ] **7.2** — Rodar backtest e registrar resultado em `docs/VALIDACAO.md`  
  `docs: registrar resultado do backtest em VALIDACAO.md`
- [ ] **7.3** — Meta: win rate ≥ 65%. Se não atingir → ajustar parâmetros RSI/MACD e repetir  
  `fix: ajustar parâmetros de estratégia conforme backtest`
- [ ] **7.4** — Documentar estratégia final em `docs/ESTRATEGIA.md`  
  `docs: documentar estratégia final em ESTRATEGIA.md`

---

### 🟦 Fase 8 — Alpha Test local 🧪 (0/3 concluídas) — PONTO DE VALIDAÇÃO

- [ ] **8.1** — Rodar alpha test de 10 ciclos rápidos:  
  `python alpha_test.py --cycles 10 --interval 30`
- [ ] **8.2** — Rodar alpha test completo: 50 ciclos, intervalo 5min:  
  `python alpha_test.py --cycles 50 --interval 300 --symbol BTCUSDT`
- [ ] **8.3** — Meta: win rate ≥ 65% → ✅ avançar para Testnet. Abaixo → ajustar e repetir

---

### 🟦 Fase 9 — Testnet Binance (0/3 concluídas)

- [ ] **9.1** — Confirmar `BINANCE_TESTNET=true` e ativar execução real de ordens  
  `feat: ativar execução de ordens no testnet`
- [ ] **9.2** — Rodar robô por 1–2 semanas monitorando `GET /metrics` diariamente
- [ ] **9.3** — Meta: win rate ≥ 62% em ≥ 30 trades → registrar em `docs/VALIDACAO.md`

---

### 🟦 Fase 10 — Dashboard Frontend (0/7 concluídas)

- [ ] **10.1** — Setup Next.js + Tailwind + Recharts no diretório `frontend/`
- [ ] **10.2** — Implementar `SignalCard` — sinal atual com força e reason
- [ ] **10.3** — Implementar `SentimentPanel` — notícias com scores FinBERT
- [ ] **10.4** — Implementar `MetricsChart` — gráficos de win rate, drawdown, profit factor
- [ ] **10.5** — Implementar `HistoryTable` — histórico de sinais do Supabase
- [ ] **10.6** — Conectar frontend ao backend e ao Supabase Realtime
- [ ] **10.7** — Deploy: frontend no Vercel + backend no Railway

---

## 📡 Rotas da API

| Rota | O que retorna |
|---|---|
| `GET /` | Status do bot |
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

## 🚀 Como instalar e rodar

```bash
git clone https://github.com/IsraelSiq/roboto.git
cd roboto
cp .env.example .env
# Preencher .env com as credenciais
pip install -r requirements.txt
# Rodar docs/supabase_schema.sql no SQL Editor do Supabase
uvicorn backend.main:app --reload --port 8000
```

---

*Desenvolvido por [Israel Siqueira](https://github.com/IsraelSiq) — projeto de estudo.*
