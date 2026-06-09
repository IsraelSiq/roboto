"""
Roboto — Ativos recomendados para day trading

Critérios de seleção:
    - Alta liquidez (spread baixo)
    - Volatilidade consistente para day trading
    - Boa correlação com análise técnica
"""

# Lista de símbolos recomendados
SYMBOLS = [
    "BTCUSDT",   # Bitcoin — mais líquido, movimentos consistentes
    "ETHUSDT",   # Ethereum — segunda maior, boa volatilidade
    "BNBUSDT",   # BNB — boa liquidez, volatilidade média
    "SOLUSDT",   # Solana — alta volatilidade, bom para day trading agressivo
]

# Símbolo padrão para operar
DEFAULT_SYMBOL = "BTCUSDT"

# Timeframe padrão
DEFAULT_INTERVAL = "5m"

# Palavras-chave para busca de notícias por símbolo
SYMBOL_KEYWORDS = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "BNBUSDT": "binance BNB",
    "SOLUSDT": "solana",
}

# Timeframes suportados
INTERVALS = {
    "1m":  "1 minuto",
    "5m":  "5 minutos",
    "15m": "15 minutos",
    "1h":  "1 hora",
    "4h":  "4 horas",
    "1d":  "1 dia",
}
