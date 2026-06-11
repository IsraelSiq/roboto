# ============================================================
# Roboto — Dockerfile multi-stage
#
# Stage 'base'  — deps comuns (sem ML)
# Stage 'bot'   — bot 24/7 (inclui FinBERT / torch)
# Stage 'api'   — FastAPI REST (sem torch, imagem menor) — usado no Render/VPS (#30)
#
# Build bot  (padrão): docker build -t roboto-bot .
# Build api:            docker build --target api -t roboto-api .
# ============================================================

FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ============================================================
# Stage: bot — inclui FinBERT (torch ≈ 2 GB)
# ============================================================
FROM base AS bot

COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt

EXPOSE 8000

CMD ["python", "-m", "backend.core.bot"]

# ============================================================
# Stage: api — FastAPI sem torch (~200 MB) (#30)
# ============================================================
FROM base AS api

EXPOSE 8000

# Liveness probe — verifica /health a cada 30s
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# WEB_CONCURRENCY controla workers do uvicorn (default 1 para free tier)
ENV WEB_CONCURRENCY=1

CMD sh -c "uvicorn backend.api.routes:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY}"
