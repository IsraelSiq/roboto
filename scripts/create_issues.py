"""
scripts/create_issues.py
Cria todas as issues pendentes do Roboto via GitHub API em lote.

Uso:
    python scripts/create_issues.py

Requer:
    GITHUB_TOKEN no .env ou variável de ambiente
    pip install requests python-dotenv
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN  = os.getenv("GITHUB_TOKEN")
OWNER  = "IsraelSiq"
REPO   = "roboto"
BASE   = f"https://api.github.com/repos/{OWNER}/{REPO}/issues"

if not TOKEN:
    print("ERRO: GITHUB_TOKEN não encontrado no .env")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ---------------------------------------------------------------------------
# Definição das issues
# ---------------------------------------------------------------------------

ISSUES = [
    # ------------------------------------------------------------------
    # GRUPO 1 — test_bot_loop / test_bot_smoke
    # TypeError: unsupported format string passed to MagicMock.__format__
    # Causa: _print_header() faz f"{self.tg._drawdown_threshold:.0f}%" mas
    #        self.tg é MagicMock sem spec — MagicMock não suporta format spec :.0f
    # ------------------------------------------------------------------
    {
        "title": "[test] TypeError em test_bot_loop/test_bot_smoke: f-string com format spec em MagicMock",
        "body": """\
## Descrição

20 testes em `test_bot_loop.py` e `test_bot_smoke.py` falham com:

```
TypeError: unsupported format string passed to MagicMock.__format__
```

## Causa raiz

`_print_header()` em `backend/core/bot.py` contém:

```python
print(f"  Drawdown alerta  : {self.tg._drawdown_threshold:.0f}% (Telegram)")
```

Nos testes, `self.tg` é um `MagicMock()` sem `spec`. Quando Python tenta aplicar o format spec `:.0f` sobre um `MagicMock`, lança `TypeError` porque `MagicMock.__format__` não suporta format specs numéricos.

## Reprodução

```bash
python -m pytest tests/test_bot_loop.py -v
```

## Solução esperada

Duas opções:
1. **Preferida** — proteger `_print_header()` com `getattr` + fallback:
   ```python
   threshold = getattr(self.tg, '_drawdown_threshold', 0)
   print(f"  Drawdown alerta  : {threshold:.0f}% (Telegram)")
   ```
2. Usar `MagicMock(spec=TelegramAlert)` no fixture do `bot_factory` — assim atributos inexistentes não são criados silenciosamente.

## Arquivos afetados

- `backend/core/bot.py` — `_print_header()`
- `tests/test_bot_loop.py` — fixture `bot_factory`
- `tests/test_bot_smoke.py` — fixture local

## Testes falhando

- `TestBotLoopBasic::test_one_cycle_completes`
- `TestBotLoopBasic::test_max_cycles_respected`
- `TestBotLoopBasic::test_balance_positive_after_run`
- `TestBotLoopBasic::test_stop_flag_ends_loop`
- `TestBotLoopSignalStrength::test_only_strong_true_ignores_weak`
- `TestBotLoopSignalStrength::test_only_strong_false_accepts_weak`
- `TestBotLoopTelegram::test_startup_called_on_run`
- `TestBotLoopTelegram::test_shutdown_called_on_run`
- `TestBotSmoke` (7 casos)
- `TestIssue6SignalCombinerPut` (8 casos)
""",
        "labels": ["bug", "tests"],
    },

    # ------------------------------------------------------------------
    # GRUPO 2 — test_risk.py: TP esperado desatualizado após issue #7
    # ------------------------------------------------------------------
    {
        "title": "[test] test_risk.py: valores esperados de TP desatualizados após issue #7 (RR=2.0)",
        "body": """\
## Descrição

2 testes em `test_risk.py` falham com `AssertionError`:

```
FAILED tests/test_risk.py::test_open_trade_call_uses_atr_when_enabled
  assert 116.0 == 110.0

FAILED tests/test_risk.py::test_open_trade_put_uses_atr_when_enabled
  assert 84.0 == 90.0
```

## Causa raiz

Após o issue #7 (SL adaptativo por ATR), o `RiskManager` passou a calcular o TP com base no risco real × `rr_ratio` (padrão `2.0`):

```
CALL: entry=100, ATR=4, mult=2.0 → risco=8 → TP = 100 + 8*2.0 = 116  ✅ correto
```

Mas os testes ainda esperavam o valor antigo (`110.0`) que corresponde a `take_profit_pct=10%`.

## Reprodução

```bash
python -m pytest tests/test_risk.py::test_open_trade_call_uses_atr_when_enabled -v
```

## Solução esperada

Atualizar os valores esperados nos testes para refletir a fórmula R:R correta:

```python
# CALL: entry=100, ATR=4, mult=2.0, rr=2.0
# risco = 4*2 = 8  →  TP = 100 + 8*2.0 = 116.0
assert trade.take_profit == 116.0

# PUT: entry=100, ATR=4, mult=2.0, rr=2.0  
# risco = 8  →  TP = 100 - 8*2.0 = 84.0
assert trade.take_profit == 84.0
```

## Arquivos afetados

- `tests/test_risk.py` — `test_open_trade_call_uses_atr_when_enabled` e `test_open_trade_put_uses_atr_when_enabled`
""",
        "labels": ["bug", "tests"],
    },

    # ------------------------------------------------------------------
    # GRUPO 3 — test_sentiment.py: fixture conftest conflita
    # ------------------------------------------------------------------
    {
        "title": "[test] test_sentiment.py: fixture autouse do conftest sobrescreve mock esperando 'negative'",
        "body": """\
## Descrição

3 testes em `test_sentiment.py` falham:

```
FAILED tests/test_sentiment.py::test_finbert_retorna_negative
  assert 'positive' == 'negative'

FAILED tests/test_sentiment.py::test_finbert_simetria_positive_vs_negative
  assert 'positive' == 'negative'

FAILED tests/test_sentiment.py::test_score_abaixo_do_threshold_vira_neutral
  assert 'positive' == 'neutral'
```

## Causa raiz

`conftest.py` registra um fixture `autouse=True` que mocka `_FINBERT_PIPELINE` com retorno fixo `positive` (score 0.82):

```python
mock_pipe.return_value = [
    [{"label": "positive", "score": 0.82}, ...]
]
```

Isso sobrescreve qualquer mock local nos testes que tentam simular um resultado `negative` ou `neutral`.

## Reprodução

```bash
python -m pytest tests/test_sentiment.py -v
```

## Solução esperada

Duas opções:
1. **Preferida** — remover `autouse=True` do `mock_finbert_pipeline` no `conftest.py` e aplicar o fixture apenas nos testes que não precisam controlar o retorno do FinBERT.
2. Nos testes de sentiment que precisam de `negative`/`neutral`, sobrescrever o mock explicitamente com `monkeypatch` local após o autouse.

## Arquivos afetados

- `tests/conftest.py` — fixture `mock_finbert_pipeline`
- `tests/test_sentiment.py` — 3 casos
""",
        "labels": ["bug", "tests"],
    },

    # ------------------------------------------------------------------
    # GRUPO 4 — BacktestEngine._sentiment vs _sentiments
    # ------------------------------------------------------------------
    {
        "title": "[bug] BacktestEngine: atributo '_sentiment' não existe (typo: deveria ser '_sentiments')",
        "body": """\
## Descrição

2 testes falham com:

```
AttributeError: 'BacktestEngine' object has no attribute '_sentiment'.
Did you mean: '_sentiments'?
```

## Causa raiz

O código de teste (ou a própria engine) referencia `self._sentiment` mas o atributo real é `self._sentiments` (plural).

## Reprodução

```bash
python -m pytest tests/backtest/test_engine_put.py::test_backtest_engine_aceita_sentiment_negative -v
python -m pytest tests/test_integration.py::TestBacktestEngineIntegration::test_backtest_sentiment_mock_expoe_source_backtest_mock -v
```

## Solução esperada

Rastrear onde `_sentiment` é usado e corrigir para `_sentiments`, ou vice-versa se o atributo foi renomeado na engine.

## Arquivos afetados

- `backend/backtest/engine.py` (verificar nome real do atributo)
- `tests/backtest/test_engine_put.py`
- `tests/test_integration.py`
""",
        "labels": ["bug"],
    },

    # ------------------------------------------------------------------
    # GRUPO 5 — test_binance_client.py: sem .env no CI/clone novo
    # ------------------------------------------------------------------
    {
        "title": "[test] test_binance_client.py: falha com ValueError quando .env não existe (clone limpo / CI)",
        "body": """\
## Descrição

10 testes em `test_binance_client.py` falham com `ERROR` em clone limpo ou CI:

```
ERROR tests/test_binance_client.py::...
  ValueError: BINANCE_API_KEY e BINANCE_SECRET devem estar no .env
```

## Causa raiz

`BinanceClient.__init__()` lança `ValueError` na inicialização quando as variáveis de ambiente não estão presentes. Os testes instanciam `BinanceClient` diretamente sem mockar a inicialização, então falham antes mesmo de executar.

## Reprodução

```bash
# em um clone limpo sem .env
python -m pytest tests/test_binance_client.py -v
```

## Solução esperada

Mockar a inicialização do `BinanceClient` nos testes unitários para não depender do `.env`:

```python
@patch.dict(os.environ, {"BINANCE_API_KEY": "fake", "BINANCE_SECRET": "fake"})
def test_get_candles_returns_dataframe():
    ...
```

Ou adicionar um fixture no `conftest.py` que injeta variáveis de ambiente falsas para todos os testes unitários.

## Arquivos afetados

- `tests/test_binance_client.py` — todos os testes
- `tests/conftest.py` — adicionar fixture de env vars
""",
        "labels": ["bug", "tests", "ci"],
    },
]

# ---------------------------------------------------------------------------
# Criação
# ---------------------------------------------------------------------------

def create_issue(issue: dict) -> dict:
    resp = requests.post(BASE, json=issue, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def main():
    print(f"Criando {len(ISSUES)} issues em {OWNER}/{REPO}...\n")
    created = []
    for i, issue in enumerate(ISSUES, 1):
        try:
            result = create_issue(issue)
            number = result["number"]
            url    = result["html_url"]
            print(f"  [{i}/{len(ISSUES)}] #{number} criada — {issue['title'][:60]}")
            print(f"           {url}")
            created.append((number, url))
        except requests.HTTPError as e:
            print(f"  [{i}/{len(ISSUES)}] ERRO: {e} — {e.response.text[:200]}")
        # GitHub API: 10 req/min para issues — espera 2s entre cada
        if i < len(ISSUES):
            time.sleep(2)

    print(f"\n✅ {len(created)}/{len(ISSUES)} issues criadas com sucesso.")
    for number, url in created:
        print(f"   #{number} — {url}")


if __name__ == "__main__":
    main()
