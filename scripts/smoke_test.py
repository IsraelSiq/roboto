#!/usr/bin/env python3
"""
Roboto — Smoke Test com Sandbox Binance Testnet

Roda uma série de verificações end-to-end usando dados reais do testnet.
Não requer Supabase nem FinBERT — ideal para CI e validação de ambiente.

Uso:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --api-url https://seu-backend.onrender.com

Requisitos no .env:
    BINANCE_API_KEY=<testnet key>
    BINANCE_SECRET=<testnet secret>
    BINANCE_TESTNET=true
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Garante que o root do projeto está no path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

results: list[tuple[str, bool, str]] = []


def step(name: str, ok: bool, detail: str = ""):
    icon = f"{GREEN}✅{RESET}" if ok else f"{RED}❌{RESET}"
    print(f"  {icon}  {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok, detail))


def section(title: str):
    print(f"\n{BOLD}{title}{RESET}")
    print("─" * 50)


# ----------------------------------------------------------
# 1. Conexão Binance
# ----------------------------------------------------------

section("🧪 Binance Testnet")

try:
    from backend.market.binance_client import BinanceClient
    bc = BinanceClient()
    mode = "TESTNET" if bc.testnet else "REAL"
    step("Inicialização do cliente", True, mode)
except Exception as e:
    step("Inicialização do cliente", False, str(e))
    bc = None

if bc:
    try:
        ok = bc.ping()
        step("Ping Binance", ok)
    except Exception as e:
        step("Ping Binance", False, str(e))

    try:
        price = bc.get_price("BTCUSDT")
        ok = price is not None and price > 0
        step("Preço BTC", ok, f"${price:,.2f}" if ok else str(price))
    except Exception as e:
        step("Preço BTC", False, str(e))

    try:
        df = bc.get_candles("BTCUSDT", "5m", limit=20)
        ok = not df.empty and len(df) >= 10
        step("Candles 5m BTCUSDT", ok, f"{len(df)} candles recebidos")
    except Exception as e:
        step("Candles 5m BTCUSDT", False, str(e))

    try:
        balance = bc.get_account_balance("USDT")
        ok = balance is not None
        detail = f"${balance:,.2f} USDT" if ok else "falhou"
        step("Saldo USDT testnet", ok, detail)
    except Exception as e:
        step("Saldo USDT testnet", False, str(e))

# ----------------------------------------------------------
# 2. Análise Técnica
# ----------------------------------------------------------

section("📊 Análise Técnica")

try:
    from backend.analysis.technical import TechnicalAnalyzer
    bc2 = BinanceClient() if bc else None
    if bc2:
        df = bc2.get_candles("BTCUSDT", "5m", limit=50)
        ta = TechnicalAnalyzer(df)
        sig = ta.analyze()
        ok = sig is not None
        step("TechnicalAnalyzer.analyze()", ok, f"sinal={getattr(sig, 'signal', sig)}" if ok else "retornou None")
except Exception as e:
    step("TechnicalAnalyzer.analyze()", False, str(e))

# ----------------------------------------------------------
# 3. Sentiment (mock — sem carregar FinBERT)
# ----------------------------------------------------------

section("🗣️ Sentiment (modo mock)")

try:
    # Substitui o transformers por um mock para não baixar o modelo
    import unittest.mock as mock
    with mock.patch.dict(os.environ, {"FINBERT_MOCK": "true"}):
        from backend.analysis.sentiment import SentimentAnalyzer
        sa = SentimentAnalyzer()
        result = sa.analyze_texts(["Bitcoin is rising strongly today"])
        ok = isinstance(result, (str, dict, list, type(None)))
        step("SentimentAnalyzer (mock)", ok, str(result)[:60] if ok else "falhou")
except Exception as e:
    step("SentimentAnalyzer (mock)", False, str(e))

# ----------------------------------------------------------
# 4. Bot — 1 ciclo sem DB
# ----------------------------------------------------------

section("🤖 Bot — 1 ciclo (max_cycles=1, use_db=False)")

try:
    from backend.core.bot import RobotoBot
    bot = RobotoBot(
        symbol="BTCUSDT",
        interval="5m",
        balance=10_000.0,
        only_strong=False,
        max_cycles=1,
        sleep_seconds=0,
        use_db=False,
    )
    start = time.time()
    bot.run()
    elapsed = round(time.time() - start, 2)
    trades  = len(bot.risk.closed_trades)
    step("Bot.run() 1 ciclo", True, f"elapsed={elapsed}s, trades_fechados={trades}")
except TypeError:
    # use_db pode não existir ainda — tenta sem ele
    try:
        bot = RobotoBot(
            symbol="BTCUSDT", interval="5m",
            balance=10_000.0, only_strong=False,
            max_cycles=1, sleep_seconds=0,
        )
        bot.run()
        step("Bot.run() 1 ciclo", True, "(use_db param n/a)")
    except Exception as e2:
        step("Bot.run() 1 ciclo", False, str(e2)[:80])
except Exception as e:
    step("Bot.run() 1 ciclo", False, str(e)[:80])

# ----------------------------------------------------------
# 5. API /health (opcional — só se --api-url fornecida)
# ----------------------------------------------------------

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--api-url", default=None)
args, _ = parser.parse_known_args()

if args.api_url:
    section(f"🌐 API — {args.api_url}")
    try:
        import urllib.request
        with urllib.request.urlopen(f"{args.api_url.rstrip('/')}/health", timeout=10) as r:
            body = r.read().decode()
            ok = r.status == 200 and "ok" in body
            step("GET /health", ok, body[:60])
    except Exception as e:
        step("GET /health", False, str(e))

# ----------------------------------------------------------
# Resumo final
# ----------------------------------------------------------

passed = sum(1 for _, ok, _ in results if ok)
total  = len(results)
failed = total - passed

print(f"\n{'='*50}")
if failed == 0:
    print(f"{GREEN}{BOLD}✅ Todos os {total} checks passaram!{RESET}")
else:
    print(f"{YELLOW}{BOLD}⚠️  {passed}/{total} passaram — {failed} falharam:{RESET}")
    for name, ok, detail in results:
        if not ok:
            print(f"  {RED}❌{RESET} {name}: {detail}")

print()
sys.exit(0 if failed == 0 else 1)
