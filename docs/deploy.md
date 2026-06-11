# Deploy Guide — Roboto

Arquitetura de produção: **Vercel** (frontend estático) + **Render** (backend FastAPI) + **Supabase** (banco).

---

## 1. Backend — Render (free tier)

### 1.1 Criar o serviço

1. Acesse [render.com](https://render.com) → **New > Web Service**.
2. Conecte o repositório `IsraelSiq/roboto`.
3. Configure:

| Campo | Valor |
|---|---|
| **Runtime** | Docker |
| **Dockerfile Path** | `./Dockerfile` |
| **Docker Command** | *(deixe vazio — usa o CMD do stage `api`)* |
| **Branch** | `main` |
| **Region** | Oregon (US West) |

> O Render usa automaticamente o **stage `api`** porque o `CMD` final no Dockerfile aponta para uvicorn sem torch.

### 1.2 Variáveis de ambiente no Render

Vocativo > seu serviço > **Environment** > adicione:

```
BINANCE_API_KEY        = <sua key>
BINANCE_SECRET         = <seu secret>
SUPABASE_URL           = https://xxxx.supabase.co
SUPABASE_KEY           = <service role key>
NEWSAPI_KEY            = <sua key>
API_TOKEN              = <token secreto>
ALLOWED_ORIGINS        = https://seu-projeto.vercel.app
WARMUP_ON_STARTUP      = false
WEB_CONCURRENCY        = 1
```

### 1.3 Health check

Render > seu serviço > **Settings > Health Check Path**: `/health`

### 1.4 Deploy Hook para CI/CD

Render > seu serviço > **Settings > Deploy Hook** — copie a URL.
Adicione como secret `RENDER_DEPLOY_HOOK` no GitHub: **repo > Settings > Secrets > Actions**.

---

## 2. Frontend — Vercel

### 2.1 Conectar o projeto

1. Acesse [vercel.com](https://vercel.com) → **Add New Project**.
2. Importe `IsraelSiq/roboto`.
3. Configure:

| Campo | Valor |
|---|---|
| **Framework Preset** | Other |
| **Root Directory** | `frontend` |
| **Build Command** | *(deixe vazio)* |
| **Output Directory** | `.` |

### 2.2 Variável de ambiente no Vercel

Vercel > seu projeto > **Settings > Environment Variables**:

```
VERCEL_API_URL = https://seu-backend.onrender.com
```

Esta variável é usada pelo `vercel.json` para fazer rewrite de `/api/*`.

### 2.3 Secrets para CI/CD

GitHub repo > **Settings > Secrets > Actions**:

| Secret | Como obter |
|---|---|
| `VERCEL_TOKEN` | vercel.com > Account Settings > Tokens |
| `VERCEL_ORG_ID` | `cat .vercel/project.json` após `vercel link` |
| `VERCEL_PROJECT_ID` | `cat .vercel/project.json` após `vercel link` |

### 2.4 Obter VERCEL_ORG_ID e VERCEL_PROJECT_ID

```bash
npm i -g vercel
cd frontend
vercel link      # faz login e associa ao projeto
cat .vercel/project.json
# { "orgId": "team_xxxx", "projectId": "prj_yyyy" }
```

---

## 3. CI/CD — resumo dos secrets necessários

| Secret | Usado por |
|---|---|
| `VERCEL_TOKEN` | deploy-frontend.yml |
| `VERCEL_ORG_ID` | deploy-frontend.yml |
| `VERCEL_PROJECT_ID` | deploy-frontend.yml |
| `RENDER_DEPLOY_HOOK` | deploy-backend.yml (Modo A) |
| `DEPLOY_HOST` | deploy-backend.yml (Modo B — VPS) |
| `DEPLOY_USER` | deploy-backend.yml (Modo B — VPS) |
| `DEPLOY_KEY` | deploy-backend.yml (Modo B — VPS) |

### Variable (não secret) para escolher o modo de deploy

GitHub repo > **Settings > Variables > Actions**:

```
DEPLOY_MODE = render    # ou: vps
```

---

## 4. Fluxo completo após configurar

```
git push main
  ├── CI (ci.yml)              → pytest + lint
  ├── Deploy Frontend           → vercel deploy --prod
  └── Deploy Backend
        ├── docker build --target api
        ├── docker push ghcr.io/.../roboto-api:latest
        └── POST RENDER_DEPLOY_HOOK   → Render faz pull + restart
```

---

## 5. Verificar deploy

```bash
# Backend
curl https://seu-backend.onrender.com/health
# {"status":"ok","ts":"2026-..."}

# Frontend
open https://seu-projeto.vercel.app
```
