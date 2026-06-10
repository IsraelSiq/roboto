# ============================================================
# Roboto — Dockerfile
# Imagem única usada tanto pela API quanto pelo bot
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# Dependências de sistema mínimas
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python (camada cacheada)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código da aplicação
COPY . .

# Porta da API (não usada pelo bot, mas mantida para o serviço api)
EXPOSE 8000

# Comando padrão: API. Sobrescrito no docker-compose para o bot.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
