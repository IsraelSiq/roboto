# ============================================================
# Roboto — Dockerfile multi-stage
#
# Stage 'base'  — deps comuns (sem ML)
# Stage 'bot'   — bot 24/7 (inclui FinBERT / torch)
# Stage 'api'   — FastAPI REST (sem torch, imagem menor)
#
# Build bot  (padrão):  docker build -t roboto-bot .
# Build api:             docker build --target api -t roboto-api .
# ============================================================

FROM python:3.11-slim AS base

WORKDIR /app

# Dependências de sistema mínimas
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# deps base (sem ML)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código da aplicação
COPY . .

# ============================================================
# Stage: bot — inclui FinBERT (torch ≈ 2 GB na imagem)
# ============================================================
FROM base AS bot

COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt

EXPOSE 8000

# Comando padrão: loop do bot
CMD ["python", "-m", "backend.core.bot"]

# ============================================================
# Stage: api — FastAPI sem torch (imagem bem menor)
# ============================================================
FROM base AS api

EXPOSE 8000

CMD ["uvicorn", "backend.api.routes:app", "--host", "0.0.0.0", "--port", "8000"]
