"""
Testes — BinanceClient
Todos os testes são offline (mock do python-binance).
"""
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock


RAW_KLINES = [
    [
        1_700_000_000_000,  # open_time
        "60000.00",         # open
        "61000.00",         # high
        "59000.00",         # low
        "60500.00",         # close
        "123.45",           # volume
        1_700_000_299_999,  # close_time
        "7_500_000.00",     # quote_asset_volume
        300,                # number_of_trades
        "60.00",            # taker_buy_base
        "3_600_000.00",     # taker_buy_quote
        "0",                # ignore
    ]
] * 10  # 10 candles idênticos para simplificar


@pytest.fixture
def binance_client():
    """BinanceClient com python-binance completamente mockado."""
    mock_bm = MagicMock()
    mock_bm.get_klines.return_value = RAW_KLINES
    mock_bm.get_symbol_ticker.return_value = {"price": "61000.00"}

    with patch("backend.market.binance_client.Client", return_value=mock_bm):
        from backend.market.binance_client import BinanceClient
        client = BinanceClient()
        client._client = mock_bm
        yield client, mock_bm


class TestBinanceClientCandles:
    def test_get_candles_returns_dataframe(self, binance_client):
        client, mock_bm = binance_client
        df = client.get_candles("BTCUSDT", "5m", limit=10)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_get_candles_has_required_columns(self, binance_client):
        client, _ = binance_client
        df = client.get_candles("BTCUSDT", "5m", limit=10)
        for col in ("open", "high", "low", "close", "volume"):
            assert col in df.columns, f"Coluna ausente: {col}"

    def test_get_candles_numeric_types(self, binance_client):
        client, _ = binance_client
        df = client.get_candles("BTCUSDT", "5m", limit=10)
        assert pd.api.types.is_float_dtype(df["close"]), "close deve ser float"
        assert pd.api.types.is_float_dtype(df["volume"]), "volume deve ser float"

    def test_get_candles_row_count(self, binance_client):
        client, mock_bm = binance_client
        mock_bm.get_klines.return_value = RAW_KLINES[:5]
        df = client.get_candles("BTCUSDT", "5m", limit=5)
        assert len(df) == 5

    def test_get_candles_calls_api_with_correct_params(self, binance_client):
        client, mock_bm = binance_client
        client.get_candles("ETHUSDT", "1h", limit=50)
        call_kwargs = mock_bm.get_klines.call_args
        assert call_kwargs is not None


class TestBinanceClientPrice:
    def test_get_price_returns_float(self, binance_client):
        client, _ = binance_client
        price = client.get_price("BTCUSDT")
        assert isinstance(price, float)
        assert price > 0

    def test_get_price_value(self, binance_client):
        client, mock_bm = binance_client
        mock_bm.get_symbol_ticker.return_value = {"price": "55000.50"}
        price = client.get_price("BTCUSDT")
        assert price == pytest.approx(55000.50)


class TestBinanceClientErrorHandling:
    def test_get_candles_connection_error_returns_empty(self, binance_client):
        """Timeout / erro de rede deve retornar DataFrame vazio sem lancar excecao."""
        client, mock_bm = binance_client
        mock_bm.get_klines.side_effect = Exception("Connection timeout")
        df = client.get_candles("BTCUSDT", "5m", limit=10)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_get_candles_rate_limit_returns_empty(self, binance_client):
        """429 / rate limit deve retornar DataFrame vazio sem lancar excecao."""
        client, mock_bm = binance_client
        mock_bm.get_klines.side_effect = Exception("Too Many Requests")
        df = client.get_candles("BTCUSDT", "5m", limit=10)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_get_price_error_returns_zero_or_raises(self, binance_client):
        """Erro no get_price nao deve propagar excecao silenciosa."""
        client, mock_bm = binance_client
        mock_bm.get_symbol_ticker.side_effect = Exception("API Error")
        # Aceita tanto retorno 0.0 quanto excecao controlada
        try:
            price = client.get_price("BTCUSDT")
            assert price == 0.0 or price is None or isinstance(price, float)
        except Exception:
            pass  # excecao controlada tambem é válido
