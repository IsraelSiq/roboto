# Deploy do Roboto

Este documento descreve as duas formas de manter o Roboto rodando 24/7.

## Opção A — Docker Compose (recomendado)

> Funciona em qualquer Linux, macOS ou Windows com Docker instalado.

### 1. Pré-requisitos

```bash
docker --version    # Docker 24+
docker compose version  # Compose v2+
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite .env com suas chaves Binance, Supabase, Telegram e API_TOKEN
```

### 3. Build e subir o bot

```bash
# Apenas o bot (uso normal)
docker compose up -d bot

# Bot + API REST
docker compose --profile api up -d
```

### 4. Monitorar

```bash
# Logs em tempo real
docker compose logs -f bot

# Status do container
docker compose ps

# Health check
docker inspect roboto-bot --format '{{.State.Health.Status}}'
```

### 5. Atualizar após `git pull`

```bash
git pull
docker compose build bot
docker compose up -d bot
```

### 6. Parar

```bash
docker compose stop bot     # para sem remover
docker compose down         # para e remove containers
```

---

## Opção B — systemd (VPS Linux sem Docker)

> Ideal para VPS bare-metal (Ubuntu/Debian) sem overhead de container.

### 1. Preparar o ambiente

```bash
# Criar usuário dedicado (boa prática de segurança)
sudo useradd -m -s /bin/bash roboto
sudo mkdir -p /opt/roboto
sudo chown roboto:roboto /opt/roboto

# Clonar o projeto
sudo -u roboto git clone https://github.com/IsraelSiq/roboto.git /opt/roboto
cd /opt/roboto

# Criar virtualenv e instalar deps
sudo -u roboto python3.11 -m venv .venv
sudo -u roboto .venv/bin/pip install -r requirements.txt -r requirements-ml.txt

# Configurar .env
sudo -u roboto cp .env.example .env
sudo -u roboto nano .env   # preencha as variáveis
```

### 2. Instalar o service

```bash
sudo cp deploy/roboto.service /etc/systemd/system/roboto.service
sudo systemctl daemon-reload
sudo systemctl enable roboto   # inicia automaticamente no boot
sudo systemctl start roboto
```

### 3. Monitorar

```bash
# Status
sudo systemctl status roboto

# Logs em tempo real
sudo journalctl -u roboto -f

# Últimas 100 linhas
sudo journalctl -u roboto -n 100
```

### 4. Atualizar

```bash
cd /opt/roboto
sudo -u roboto git pull
sudo -u roboto .venv/bin/pip install -r requirements.txt -r requirements-ml.txt
sudo systemctl restart roboto
```

### 5. Parar

```bash
sudo systemctl stop roboto
```

---

## Qual escolher?

| Critério | Docker Compose | systemd |
|---|---|---|  
| Isolamento | ✅ Container isolado | ❌ Processo no host |
| Portabilidade | ✅ Funciona em qualquer OS | ❌ Apenas Linux |
| Facilidade de update | ✅ `docker compose build` | ⚠️ Manual |
| Overhead de memória | ⚠️ +~50 MB | ✅ Zero overhead |
| Restart automático | ✅ `unless-stopped` | ✅ `Restart=always` |
| Acesso aos logs | ✅ `docker compose logs` | ✅ `journalctl` |
