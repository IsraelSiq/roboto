# Infraestrutura — Roboto

Arquitetura completa usando **GitHub + Vercel + Supabase**.

---

## Visão Geral

```
┌─────────────────────────────────────────────────────────┐
│                        GITHUB                           │
│  Repositório: IsraelSiq/roboto                          │
│  ├── main branch → deploy automático                    │
│  ├── feature branches → Pull Requests                   │
│  └── GitHub Actions → CI (testes automáticos)           │
└────────────┬────────────────────┬───────────────────────┘
             │                    │
             ▼                    ▼
┌────────────────────┐  ┌─────────────────────────────────┐
│      VERCEL        │  │           SUPABASE              │
│                    │  │                                 │
│  Frontend          │  │  PostgreSQL (banco de dados)    │
│  Next.js dashboard │  │  ├── signals                   │
│  Deploy automático │  │  ├── trades                    │
│  a cada push/PR    │  │  ├── backtest_runs              │
│                    │  │  └── news_cache                 │
│  Env vars:         │  │                                 │
│  NEXT_PUBLIC_      │  │  Auth + RLS (Row Level Security)│
│  SUPABASE_URL      │  │  Realtime (updates ao vivo)     │
│  SUPABASE_ANON_KEY │  │  REST API automática            │
└────────────────────┘  └────────────────┬────────────────┘
                                         │
             ┌───────────────────────────┘
             ▼
┌─────────────────────────────────────────────────────────┐
│                  BACKEND PYTHON                         │
│  FastAPI rodando localmente ou no Railway               │
│  ├── Lê candles da Binance API                          │
│  ├── Busca notícias via NewsAPI                         │
│  ├── Roda FinBERT para sentiment                        │
│  ├── Gera sinal combinado (técnico + sentiment)         │
│  └── Salva resultados no Supabase via supabase-py       │
└─────────────────────────────────────────────────────────┘
```

---

## GitHub

### Estrutura de branches

| Branch | Propósito |
|---|---|
| `main` | Produção — deploy automático no Vercel |
| `develop` | Integração de features |
| `feat/fase-X-nome` | Uma feature por fase |
| `fix/nome` | Correções |

### Fluxo de trabalho

```bash
# Criar branch para uma feature
git checkout -b feat/fase-1-binance-client

# Desenvolver, testar, commitar
git add .
git commit -m "feat: implementar binance_client.py com conexão testnet"

# Push e abrir PR para main
git push origin feat/fase-1-binance-client
```

### GitHub Actions (CI)

Arquivo: `.github/workflows/ci.yml`
- Roda testes automaticamente em todo PR
- Bloqueia merge se testes falharem

---

## Vercel

### Configuração

1. Acesse [vercel.com](https://vercel.com) → **Add New Project**
2. Importe o repositório `IsraelSiq/roboto`
3. Configure **Root Directory** como `frontend`
4. Adicione as variáveis de ambiente:

| Variável | Valor |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | URL do seu projeto Supabase |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Anon key do Supabase |
| `NEXT_PUBLIC_API_URL` | URL do backend (Railway ou local) |

### Deploy automático

- **Push na `main`** → deploy em produção
- **Pull Request** → deploy de preview com URL única

---

## Supabase

### Configuração

1. Acesse [supabase.com](https://supabase.com) → **New Project**
2. Anote a **URL** e a **anon key** (Settings → API)
3. Vá em **SQL Editor** e execute o arquivo `docs/supabase_schema.sql`
4. Ative **Realtime** nas tabelas `signals` e `trades` (Table Editor → Replication)

### Tabelas

| Tabela | Quem escreve | Quem lê |
|---|---|---|
| `signals` | Backend Python | Frontend (dashboard) |
| `trades` | Backend Python | Frontend (dashboard) |
| `backtest_runs` | Backend Python | Frontend (histórico) |
| `news_cache` | Backend Python | Backend (cache) |

### Realtime

O frontend pode se inscrever para receber sinais ao vivo:

```typescript
// frontend/src/services/realtime.ts
const channel = supabase
  .channel('signals')
  .on('postgres_changes', {
    event: 'INSERT',
    schema: 'public',
    table: 'signals'
  }, (payload) => {
    // Atualizar SignalCard automaticamente
    setCurrentSignal(payload.new)
  })
  .subscribe()
```

### Segurança (RLS)

- **Frontend (anon key)**: só leitura
- **Backend Python (service_role key)**: leitura + escrita
- Nunca exponha a `service_role` key no frontend!

---

## Variáveis de ambiente por plataforma

### Backend local (`.env`)
```env
BINANCE_API_KEY=...
BINANCE_SECRET=...
BINANCE_TESTNET=true
NEWSAPI_KEY=...
SUPABASE_URL=...
SUPABASE_KEY=...  ← service_role key (nunca no frontend!)
```

### Vercel (painel → Environment Variables)
```env
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...  ← anon key (segura para o frontend)
NEXT_PUBLIC_API_URL=...            ← URL do backend
```

### Railway (se usar para o backend)
```env
# Mesmas variáveis do .env local
```
