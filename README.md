# 🤖 Roboto — Bot de Trading Automatizado

Bot de trading para criptomoedas com análise técnica (RSI, MACD, EMA, Bollinger Bands) + Sentiment Analysis (FinBERT) + Risk Management completo.

## Arquitetura

```
roboto/
├── backend/
│   ├── market/         # BinanceClient (coleta de candles)
│   ├── analysis/       # TechnicalAnalyzer + SentimentAnalyzer + SignalCombiner
│   ├── risk/           # RiskManager + PerformanceMetrics
│   ├── core/           # RobotoBot (loop principal)
│   └── api/            # FastAPI REST
├── dashboard/          # Streamlit UI
└── .env
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # preencha as chaves
```

## Rodando

### 1. API (backend)
```bash
python -m backend.api.routes
# ou
uvicorn backend.api.routes:app --reload --port 8000
```

### 2. Dashboard
```bash
streamlit run dashboard/app.py
```

### 3. Bot direto (sem dashboard)
```bash
python -m backend.core.bot --symbol BTCUSDT --interval 5m --cycles 10
```

## Variáveis de Ambiente (.env)

```
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_TESTNET=true
NEWSAPI_KEY=...
SUPABASE_URL=...
SUPABASE_KEY=...
```

## Fases do projeto

| Fase | Módulo | Status |
|------|--------|--------|
| 1 | Binance Client | ✅ |
| 2 | Análise Técnica | ✅ |
| 3 | Sentiment FinBERT | ✅ |
| 4 | Núcleo de Sinais | ✅ |
| 5 | Risk Management | ✅ |
| 6 | Loop Automático | ✅ |
| 7A | Dashboard + API | ✅ |
| 7B | Deploy (Supabase + Vercel) | 🔜 |
| 7C | Backtesting | 🔜 |
