import os
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()


@dataclass
class Config:
    # Binance
    BINANCE_API_KEY: str
    BINANCE_SECRET: str
    BINANCE_TESTNET: bool

    # NewsAPI
    NEWSAPI_KEY: str

    # Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # Configurações do robô
    DEFAULT_SYMBOL: str
    DEFAULT_TIMEFRAME: str
    MAX_TRADES_PER_DAY: int
    STOP_LOSS_PCT: float
    TAKE_PROFIT_PCT: float
    MAX_DRAWDOWN_PCT: float

    # App
    ENV: str
    PORT: int


def load_config() -> Config:
    """Carrega e valida todas as variáveis de ambiente."""
    missing = []

    required_keys = [
        "BINANCE_API_KEY",
        "BINANCE_SECRET",
        "NEWSAPI_KEY",
        "SUPABASE_URL",
        "SUPABASE_KEY",
    ]

    for key in required_keys:
        if not os.getenv(key):
            missing.append(key)

    if missing:
        raise EnvironmentError(
            f"❌ Variáveis de ambiente ausentes: {', '.join(missing)}\n"
            f"   Copie .env.example para .env e preencha as credenciais."
        )

    return Config(
        BINANCE_API_KEY=os.getenv("BINANCE_API_KEY"),
        BINANCE_SECRET=os.getenv("BINANCE_SECRET"),
        BINANCE_TESTNET=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
        NEWSAPI_KEY=os.getenv("NEWSAPI_KEY"),
        SUPABASE_URL=os.getenv("SUPABASE_URL"),
        SUPABASE_KEY=os.getenv("SUPABASE_KEY"),
        DEFAULT_SYMBOL=os.getenv("DEFAULT_SYMBOL", "BTCUSDT"),
        DEFAULT_TIMEFRAME=os.getenv("DEFAULT_TIMEFRAME", "5m"),
        MAX_TRADES_PER_DAY=int(os.getenv("MAX_TRADES_PER_DAY", "10")),
        STOP_LOSS_PCT=float(os.getenv("STOP_LOSS_PCT", "0.05")),
        TAKE_PROFIT_PCT=float(os.getenv("TAKE_PROFIT_PCT", "0.10")),
        MAX_DRAWDOWN_PCT=float(os.getenv("MAX_DRAWDOWN_PCT", "0.20")),
        ENV=os.getenv("ENV", "development"),
        PORT=int(os.getenv("PORT", "8000")),
    )


# Instância global
config = load_config() if os.getenv("BINANCE_API_KEY") else None
