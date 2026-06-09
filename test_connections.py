#!/usr/bin/env python3
"""
Roboto — Teste de Instalação + Conexões
Valida se todas as dependências estão instaladas e as APIs conectadas.

Uso:
    python test_connections.py
"""

import sys

PASS = "✅"
FAIL = "❌"

results = []


def check(label, ok, detail=""):
    icon = PASS if ok else FAIL
    msg = f"{icon} {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append(ok)


print("\n🤖 Roboto — Testando instalação e conexões...\n")
print("=" * 55)

# ============================================================
# 1. Dependências
# ============================================================
print("\n[1/5] Dependências instaladas")

try:
    import pandas as pd
    check("  pandas", True, pd.__version__)
except ImportError:
    check("  pandas", False, "nao instalado")

try:
    import numpy as np
    check("  numpy", True, np.__version__)
except ImportError:
    check("  numpy", False, "nao instalado")

try:
    import pandas_ta as ta
    check("  pandas-ta", True, getattr(ta, "__version__", "ok"))
except ImportError:
    check("  pandas-ta", False, "nao instalado — rode: pip install pandas-ta-classic")

try:
    from binance.client import Client
    check("  python-binance", True)
except ImportError:
    check("  python-binance", False, "nao instalado")

try:
    from newsapi import NewsApiClient
    check("  newsapi-python", True)
except ImportError:
    check("  newsapi-python", False, "nao instalado")

try:
    from supabase import create_client
    check("  supabase", True)
except ImportError:
    check("  supabase", False, "nao instalado")

try:
    import fastapi
    check("  fastapi", True, fastapi.__version__)
except ImportError:
    check("  fastapi", False, "nao instalado")

try:
    import torch
    check("  torch", True, torch.__version__)
except ImportError:
    check("  torch", False, "nao instalado — rode: pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu")

try:
    import transformers
    check("  transformers", True, transformers.__version__)
except ImportError:
    check("  transformers", False, "nao instalado")

# ============================================================
# 2. Variáveis de ambiente
# ============================================================
print("\n[2/5] Variáveis de ambiente")

from dotenv import load_dotenv
import os
load_dotenv()

exemplos = [
    "sua_binance_api_key", "seu_binance_secret",
    "sua_newsapi_key", "https://xxxx.supabase.co"
]

required_vars = [
    "BINANCE_API_KEY", "BINANCE_SECRET",
    "NEWSAPI_KEY", "SUPABASE_URL", "SUPABASE_KEY",
]

all_vars_ok = True
for var in required_vars:
    val = os.getenv(var)
    ok = bool(val and val not in exemplos)
    check(f"  {var}", ok, "ok" if ok else "NAO configurada ou com valor de exemplo")
    if not ok:
        all_vars_ok = False

if not all_vars_ok:
    print(f"\n{FAIL} Preencha o .env antes de continuar.")
    sys.exit(1)

# ============================================================
# 3. Binance Testnet
# ============================================================
print("\n[3/5] Binance Testnet")
try:
    from binance.client import Client

    client = Client(
        os.getenv("BINANCE_API_KEY"),
        os.getenv("BINANCE_SECRET"),
        testnet=True
    )

    status = client.get_system_status()
    check("  Status do servidor", status.get("status") == 0, "online")

    account = client.get_account()
    check("  Acesso à conta", True, f"canTrade={account.get('canTrade')}")

    candles = client.get_klines(symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_5MINUTE, limit=3)
    check("  Busca de candles BTCUSDT 5m", len(candles) > 0, f"{len(candles)} candles recebidos")

except Exception as e:
    check("  Binance Testnet", False, str(e))

# ============================================================
# 4. NewsAPI
# ============================================================
print("\n[4/5] NewsAPI")
try:
    from newsapi import NewsApiClient

    newsapi = NewsApiClient(api_key=os.getenv("NEWSAPI_KEY"))
    resp = newsapi.get_top_headlines(q="bitcoin", language="en", page_size=1)
    ok = resp.get("status") == "ok"
    check("  Conexão NewsAPI", ok, f"{resp.get('totalResults')} resultados" if ok else str(resp))

except Exception as e:
    check("  NewsAPI", False, str(e))

# ============================================================
# 5. Supabase
# ============================================================
print("\n[5/5] Supabase")
try:
    from supabase import create_client

    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

    r1 = sb.table("signals").select("id").limit(1).execute()
    check("  Conexão Supabase", True, "conectado")
    check("  Tabela 'signals'", True, f"{len(r1.data)} registro(s)")

    r2 = sb.table("trades").select("id").limit(1).execute()
    check("  Tabela 'trades'", True, f"{len(r2.data)} registro(s)")

except Exception as e:
    msg = str(e)
    if "does not exist" in msg:
        check("  Tabelas Supabase", False, "rode o docs/supabase_schema.sql no SQL Editor do Supabase")
    else:
        check("  Supabase", False, msg)

# ============================================================
# Resultado final
# ============================================================
print("\n" + "=" * 55)
total = len(results)
passed = sum(results)
failed = total - passed

if failed == 0:
    print(f"\n{PASS} Tudo certo! {passed}/{total} checks passaram.")
    print("   Ambiente pronto. Pode avançar para a Fase 1 🚀\n")
else:
    print(f"\n{FAIL} {failed}/{total} checks falharam. Corrija os erros acima.\n")
    sys.exit(1)
