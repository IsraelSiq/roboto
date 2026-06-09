-- ============================================================
-- Roboto — Schema Supabase
-- Execute este arquivo no SQL Editor do seu projeto Supabase
-- ============================================================

-- Tabela de sinais gerados
CREATE TABLE IF NOT EXISTS signals (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    technical_signal TEXT NOT NULL,   -- CALL | PUT | AGUARDAR
    sentiment_signal TEXT NOT NULL,   -- positive | negative | neutral
    final_decision TEXT NOT NULL,     -- CALL_FORTE | PUT_FORTE | CALL_FRACO | PUT_FRACO | AGUARDAR
    rsi NUMERIC,
    macd NUMERIC,
    ema50 NUMERIC,
    sentiment_score NUMERIC,
    reason TEXT,
    cycle INTEGER
);

-- Tabela de trades executados
CREATE TABLE IF NOT EXISTS trades (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    signal_id UUID REFERENCES signals(id),
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,          -- CALL | PUT
    strength TEXT NOT NULL,           -- FORTE | FRACO
    result TEXT,                      -- WIN | LOSS | PENDING
    pnl_pct NUMERIC,                  -- % de lucro ou perda
    entry_price NUMERIC,
    exit_price NUMERIC,
    mode TEXT DEFAULT 'paper'         -- paper | testnet | real
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_result ON trades(result);
