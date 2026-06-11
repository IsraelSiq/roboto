#!/usr/bin/env python3
"""
Roboto — Smoke Test com Sandbox Binance Testnet

Verificações end-to-end usando dados reais do testnet.
Não requer Supabase nem FinBERT na memória — ideal para CI e validação de ambiente.

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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

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

bc = None
try:
    from backend.market.binance_client import BinanceClient
    bc = BinanceClient()
    mode = "TESTNET" if bc.testnet else "REAL"
    step("Inicialização do cliente", True, mode)
except Exception as e:
    step("Inicialização do cliente", False, str(e))

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
        # 100 candles para satisfazer min_candles=60 do TechnicalAnalyzer
        df_candles = bc.get_candles("BTCUSDT", "5m", limit=100)
        ok = not df_candles.empty and len(df_candles) >= 20
        step("Candles 5m BTCUSDT", ok, f"{len(df_candles)} candles recebidos")
    except Exception as e:
        step("Candles 5m BTCUSDT", False, str(e))
        df_candles = None

    try:
        balance = bc.get_account_balance("USDT")
        ok = balance is not None
        step("Saldo USDT testnet", ok, f"${balance:,.2f} USDT" if ok else "falhou")
    except Exception as e:
        step("Saldo USDT testnet", False, str(e))


# ----------------------------------------------------------
# 2. Análise Técnica
# ----------------------------------------------------------

section("📊 Análise Técnica")

try:
    from backend.analysis.technical import TechnicalAnalyzer
    # TechnicalAnalyzer() sem args; analyze(df) recebe o DataFrame
    ta = TechnicalAnalyzer()
    if bc and df_candles is not None and not df_candles.empty:
        sig = ta.analyze(df_candles)
        ok = sig is not None
        step("TechnicalAnalyzer.analyze(df)", ok,
             f"sinal={sig.signal} | {sig.reason[:60]}" if ok else "retornou None")
    else:
        step("TechnicalAnalyzer.analyze(df)", False, "candles indisponíveis")
except Exception as e:
    step("TechnicalAnalyzer.analyze(df)", False, str(e))


# ----------------------------------------------------------
# 3. Sentiment (mock — sem carregar FinBERT)
# ----------------------------------------------------------

section("🗣️ Sentiment (mock — analyze_news com lista fake)")

try:
    from backend.analysis.sentiment import SentimentAnalyzer
    import unittest.mock as mock

    # Mock do pipeline FinBERT para não baixar o modelo no smoke test
    fake_pipeline_output = [[{"label": "positive", "score": 0.85},
                              {"label": "negative", "score": 0.10},
                              {"label": "neutral",  "score": 0.05}]]

    sa = SentimentAnalyzer()
    with mock.patch("backend.analysis.sentiment._FINBERT_PIPELINE", fake_pipeline_output[0]):
        # Simula pipeline carregado retornando lista de scores
        import backend.analysis.sentiment as _sa_mod
        _sa_mod._FINBERT_PIPELINE = lambda text: fake_pipeline_output[0]

        fake_news = [
            {"title": "Bitcoin surges to new highs", "description": "BTC up 5%"},
            {"title": "Crypto market bullish",       "description": "ETH also rises"},
        ]
        result = sa.analyze_news(fake_news)
        ok = result is not None and result.signal in ("positive", "negative", "neutral")
        step("SentimentAnalyzer.analyze_news()", ok,
             f"signal={result.signal} score={result.score} source={result.source}" if ok else str(result))
except Exception as e:
    step("SentimentAnalyzer.analyze_news()", False, str(e))


# ----------------------------------------------------------
# 4. Bot — 1 ciclo sem DB
# ----------------------------------------------------------

section("🤖 Bot — 1 ciclo (max_cycles=1)")

try:
    from backend.core.bot import RobotoBot
    kwargs = dict(
        symbol="BTCUSDT", interval="5m",
        balance=10_000.0, only_strong=False,
        max_cycles=1, sleep_seconds=0,
    )
    try:
        bot = RobotoBot(**kwargs, use_db=False)
    except TypeError:
        bot = RobotoBot(**kwargs)  # use_db não existe ainda

    start = time.time()
    bot.run()
    elapsed = round(time.time() - start, 2)
    trades  = len(bot.risk.closed_trades)
    step("Bot.run() 1 ciclo", True, f"elapsed={elapsed}s, trades_fechados={trades}")
except Exception as e:
    step("Bot.run() 1 ciclo", False, str(e)[:100])


# ----------------------------------------------------------
# 5. API /health (opcional)
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
