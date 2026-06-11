# Teste com Sandbox Binance Testnet

Guia rápido para rodar o Roboto com dados reais usando o ambiente sandbox da Binance.
Nenhum dinheiro real é usado — a testnet fornece ~10.000 USDT virtual.

---

## 1. Criar conta e keys na Binance Testnet

1. Acesse **[testnet.binance.vision](https://testnet.binance.vision)**
2. Clique em **"Log In with GitHub"**
3. Após login, vá em **"API Management"**
4. Clique em **"Generate HMAC_SHA256 Key"**
5. Copie a **API Key** e o **Secret Key** — o secret só aparece uma vez!

---

## 2. Configurar o .env

```bash
cp .env.example .env
```

Edite o `.env`:

```dotenv
BINANCE_API_KEY=cole_sua_testnet_api_key
BINANCE_SECRET=cole_seu_testnet_secret
BINANCE_TESTNET=true
```

O resto pode ficar com os defaults para o smoke test (Supabase/NewsAPI não são necessários).

---

## 3. Rodar o Smoke Test

```bash
# Instalar dependências (já feito se rodou pip install -r requirements.txt)
pip install -r requirements.txt

# Smoke test local
python scripts/smoke_test.py

# Smoke test + API (se o backend já estiver rodando)
uvicorn backend.api.routes:app --port 8000 &
python scripts/smoke_test.py --api-url http://localhost:8000

# Smoke test contra produção
python scripts/smoke_test.py --api-url https://seu-backend.onrender.com
```

Saída esperada:

```
🧪 Binance Testnet
──────────────────────────────────────────────────
  ✅  Inicialização do cliente — TESTNET
  ✅  Ping Binance
  ✅  Preço BTC — $107,432.50
  ✅  Candles 5m BTCUSDT — 20 candles recebidos
  ✅  Saldo USDT testnet — $10,000.00 USDT

📊 Análise Técnica
...
  ✅  TechnicalAnalyzer.analyze() — sinal=AGUARDAR

🤖 Bot — 1 ciclo (max_cycles=1, use_db=False)
...
  ✅  Bot.run() 1 ciclo — elapsed=1.2s, trades_fechados=0

==================================================
✅ Todos os 7 checks passaram!
```

---

## 4. Comportamento do testnet

| Aspecto | Testnet | Real |
|---|---|---|
| Klines/candles | Esparsos — bot usa API pública | Dados completos |
| Preço BTC | Espelhado do real (réplica) | Tempo real |
| Saldo inicial | ~10.000 USDT virtual | Seu saldo real |
| Ordens | Simuladas (não executam no mercado) | Executadas |
| Keys expiram | Periódicamente — regere se precisar | Não expiram |

> **Nota:** O Roboto não envia ordens reais para a Binance — ele usa o saldo como referência
> para cálculos de risco. As decisões (CALL/PUT) são salvas no Supabase e exibidas no dashboard.

---

## 5. Executar o bot completo (1 sessão de teste)

```bash
# Inicia a API em background
uvicorn backend.api.routes:app --port 8000 &

# Dispara o bot via API (1 ciclo para testar)
curl -X POST http://localhost:8000/bot/start \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT","interval":"5m","balance":10000,"only_strong":false,"max_cycles":3,"sleep_seconds":5}'

# Acompanha o status
curl http://localhost:8000/status | python -m json.tool

# Para o bot
curl -X POST http://localhost:8000/bot/stop

# Verifica se o sinal foi salvo
curl 'http://localhost:8000/signals?limit=5' | python -m json.tool
```

---

## 6. Checklist antes de producão real

- [ ] Smoke test passou com `BINANCE_TESTNET=true`
- [ ] Dashboard Vercel acessível publicamente
- [ ] `ALLOWED_ORIGINS` atualizado com URL real do Vercel
- [ ] `BINANCE_TESTNET=false` no Render (com keys reais)
- [ ] `API_TOKEN` definido e testado
- [ ] `only_strong=true` no bot (evita operações fracas)
- [ ] Drawdown limit configurado (padrão: 15%)
