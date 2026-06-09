"""
Testes — FastAPI endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from backend.api.routes import app

client = TestClient(app)


class TestAPIHealth:
    def test_root(self):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestAPIStatus:
    def test_status_no_bot(self):
        r = client.get("/status")
        assert r.status_code == 200
        data = r.json()
        assert data["running"] is False
        assert data["balance"] is None


class TestAPIPrice:
    def test_price_endpoint(self):
        with patch("backend.api.routes._client") as mock_client:
            mock_client.get_price.return_value = 61000.0
            r = client.get("/price?symbol=BTCUSDT")
            assert r.status_code == 200
            assert r.json()["price"] == 61000.0


class TestAPICandles:
    def test_candles_endpoint(self):
        import pandas as pd
        import numpy as np
        mock_df = pd.DataFrame({
            "open_time": pd.date_range("2026-01-01", periods=50, freq="5min"),
            "open":   np.random.uniform(59000, 61000, 50),
            "high":   np.random.uniform(61000, 62000, 50),
            "low":    np.random.uniform(58000, 59000, 50),
            "close":  np.random.uniform(59000, 61000, 50),
            "volume": np.random.uniform(100, 1000, 50),
        })
        with patch("backend.api.routes._client") as mock_client:
            mock_client.get_candles.return_value = mock_df
            r = client.get("/candles?symbol=BTCUSDT&interval=5m&limit=50")
            assert r.status_code == 200
            assert "candles" in r.json()


class TestAPIBotControl:
    def test_stop_when_not_running(self):
        r = client.post("/bot/stop")
        assert r.status_code == 200
        assert r.json()["status"] == "not_running"

    def test_resume_when_no_bot(self):
        r = client.post("/bot/resume")
        assert r.status_code == 200
        assert r.json()["status"] == "no_bot"
