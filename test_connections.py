#!/usr/bin/env python3
"""
Roboto — Teste de Conexões
Valida se todas as API keys e conexões estão funcionando corretamente.

Uso:
    python test_connections.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

results = []


def check(label, ok, detail=""):
    icon = PASS if ok else FAIL
    msg = f"{icon} {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append(ok)


print("\n🤖 Roboto — Testando conexões...\n")
print("=" * 50)

# ============================================================
# 1. Variáveis de ambiente
# ============================================================
print("\n[1/3] Variáveis de ambiente")

required_vars = [
    "BINANCE_API_KEY",
    "BINANCE_SECRET",
    "NEWSAPI_KEY",
    "SUPABASE_URL",
    "SUPABASE_KEY",
]

all_vars_ok = True
for var in required_vars:
    val = os.getenv(var)
    ok = bool(val and val not in ["sua_binance_api_key", "seu_binance_secret",
                                    "sua_newsapi_key", "sua_supabase_anon_key",
                                    "https://xxxx.supabase.co"])
    check(f"  {var}", ok, "configurada" if ok else "NAO configurada ou com valor de exemplo")
    if not ok:
        all_vars_ok = False

if not all_vars_ok:
    print(f"\n{FAIL} Preencha todas as variáveis no .env antes de continuar.")
    sys.exit(1)

# ============================================================
# 2. Binance Testnet
# ============================================================
print("\n[2/3] Binance Testnet")
try:
    from binance.client import Client

    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_SECRET")
    testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    client = Client(api_key, api_secret, testnet=testnet)

    # Testa status do servidor
    status = client.get_system_status()
    server_ok = status.get("status") == 0
    check("  Status do servidor Binance", server_ok,
          "online" if server_ok else f"status: {status}")

    # Testa acesso à conta
    account = client.get_account()
    can_trade = account.get("canTrade", False)
    check("  Acesso à conta", True, f"canTrade={can_trade}")

    # Testa busca de candles
    candles = client.get_klines(symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_5MINUTE, limit=3)
    check("  Busca de candles BTCUSDT (5m)", len(candles) > 0,
          f"{len(candles)} candles recebidos")

except ImportError:
    check("  python-binance instalado", False, "rode: pip install -r requirements.txt")
except Exception as e:
    check("  Conexão Binance Testnet", False, str(e))

# ============================================================
# 3. NewsAPI
# ============================================================
print("\n[3/3] NewsAPI")
try:
    from newsapi import NewsApiClient

    newsapi = NewsApiClient(api_key=os.getenv("NEWSAPI_KEY"))
    response = newsapi.get_top_headlines(q="bitcoin", language="en", page_size=1)
    ok = response.get("status") == "ok"
    total = response.get("totalResults", 0)
    check("  Conexão NewsAPI", ok, f"{total} resultados para 'bitcoin'" if ok else str(response))

except ImportError:
    check("  newsapi-python instalado", False, "rode: pip install -r requirements.txt")
except Exception as e:
    check("  Conexão NewsAPI", False, str(e))

# ============================================================
# 4. Supabase
# ============================================================
print("\n[4/4] Supabase")
try:
    from supabase import create_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    supabase = create_client(url, key)

    # Testa leitura da tabela signals
    response = supabase.table("signals").select("id").limit(1).execute()
    check("  Conexão Supabase", True, "conectado")
    check("  Tabela 'signals' existe", True,
          f"{len(response.data)} registro(s) encontrado(s)")

    # Testa leitura da tabela trades
    response2 = supabase.table("trades").select("id").limit(1).execute()
    check("  Tabela 'trades' existe", True,
          f"{len(response2.data)} registro(s) encontrado(s)")

except ImportError:
    check("  supabase instalado", False, "rode: pip install -r requirements.txt")
except Exception as e:
    error_msg = str(e)
    if "relation" in error_msg and "does not exist" in error_msg:
        check("  Tabelas Supabase", False,
              "tabelas nao encontradas — rode o docs/supabase_schema.sql no SQL Editor")
    else:
        check("  Conexão Supabase", False, error_msg)

# ============================================================
# Resultado final
# ============================================================
print("\n" + "=" * 50)
total = len(results)
passed = sum(results)
failed = total - passed

if failed == 0:
    print(f"\n{PASS} Tudo certo! {passed}/{total} checks passaram.")
    print("   Pode avançar para a Fase 1 🚀\n")
else:
    print(f"\n{FAIL} {failed}/{total} checks falharam.")
    print("   Corrija os erros acima antes de avançar.\n")
    sys.exit(1)
