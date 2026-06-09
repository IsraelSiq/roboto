-- ============================================================
-- Roboto — Schema Supabase (completo)
-- Execute este arquivo no SQL Editor do seu projeto Supabase
-- ============================================================

-- Habilitar extensão UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- TABELA: signals
-- Todos os sinais gerados pelo robô (técnico + sentiment)
-- ============================================================
CREATE TABLE IF NOT EXISTS signals (
    id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    symbol           TEXT        NOT NULL,                -- ex: BTCUSDT
    timeframe        TEXT        NOT NULL,                -- ex: 5m
    technical_signal TEXT        NOT NULL,                -- CALL | PUT | AGUARDAR
    sentiment_signal TEXT        NOT NULL,                -- positive | negative | neutral
    final_decision   TEXT        NOT NULL,                -- CALL_FORTE | PUT_FORTE | CALL_FRACO | PUT_FRACO | AGUARDAR
    rsi              NUMERIC,
    macd             NUMERIC,
    macd_signal      NUMERIC,
    ema50            NUMERIC,
    bb_upper         NUMERIC,
    bb_lower         NUMERIC,
    current_price    NUMERIC,
    sentiment_score  NUMERIC,
    news_count       INTEGER     DEFAULT 0,
    reason           TEXT,
    cycle            INTEGER,
    mode             TEXT        DEFAULT 'paper'          -- paper | testnet | real
);

-- ============================================================
-- TABELA: trades
-- Trades executados (ou simulados) com base nos sinais
-- ============================================================
CREATE TABLE IF NOT EXISTS trades (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    closed_at    TIMESTAMPTZ,
    signal_id    UUID        REFERENCES signals(id) ON DELETE SET NULL,
    symbol       TEXT        NOT NULL,
    direction    TEXT        NOT NULL,                    -- CALL | PUT
    strength     TEXT        NOT NULL,                   -- FORTE | FRACO
    entry_price  NUMERIC,
    exit_price   NUMERIC,
    pnl_pct      NUMERIC,                                -- % lucro ou perda
    result       TEXT        DEFAULT 'PENDING',          -- WIN | LOSS | PENDING
    mode         TEXT        DEFAULT 'paper'             -- paper | testnet | real
);

-- ============================================================
-- TABELA: backtest_runs
-- Histórico de cada execução de backtest
-- ============================================================
CREATE TABLE IF NOT EXISTS backtest_runs (
    id             UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    symbol         TEXT        NOT NULL,
    timeframe      TEXT        NOT NULL,
    period_start   DATE        NOT NULL,
    period_end     DATE        NOT NULL,
    total_trades   INTEGER,
    win_rate       NUMERIC,
    profit_factor  NUMERIC,
    max_drawdown   NUMERIC,
    sharpe_ratio   NUMERIC,
    approved       BOOLEAN     DEFAULT FALSE,             -- true se win_rate >= 65%
    notes          TEXT
);

-- ============================================================
-- TABELA: news_cache
-- Cache de notícias para evitar chamadas duplicadas à NewsAPI
-- ============================================================
CREATE TABLE IF NOT EXISTS news_cache (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    fetched_at   TIMESTAMPTZ DEFAULT NOW(),
    symbol       TEXT        NOT NULL,
    title        TEXT        NOT NULL,
    description  TEXT,
    source       TEXT,
    url          TEXT,
    sentiment    TEXT,                                   -- positive | negative | neutral
    score        NUMERIC
);

-- ============================================================
-- ÍNDICES — performance de consultas
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_signals_created_at  ON signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_symbol      ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_decision    ON signals(final_decision);
CREATE INDEX IF NOT EXISTS idx_signals_mode        ON signals(mode);
CREATE INDEX IF NOT EXISTS idx_trades_created_at   ON trades(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_result       ON trades(result);
CREATE INDEX IF NOT EXISTS idx_trades_mode         ON trades(mode);
CREATE INDEX IF NOT EXISTS idx_news_cache_symbol   ON news_cache(symbol);
CREATE INDEX IF NOT EXISTS idx_news_cache_fetched  ON news_cache(fetched_at DESC);

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- Necessário para acessar o Supabase via anon key do frontend
-- ============================================================
ALTER TABLE signals        ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades         ENABLE ROW LEVEL SECURITY;
ALTER TABLE backtest_runs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE news_cache     ENABLE ROW LEVEL SECURITY;

-- Política: leitura pública (anon pode ler — necessário para o dashboard)
CREATE POLICY "public read signals"       ON signals        FOR SELECT USING (true);
CREATE POLICY "public read trades"        ON trades         FOR SELECT USING (true);
CREATE POLICY "public read backtest_runs" ON backtest_runs  FOR SELECT USING (true);
CREATE POLICY "public read news_cache"    ON news_cache     FOR SELECT USING (true);

-- Política: escrita apenas via service_role (backend Python)
CREATE POLICY "service insert signals"       ON signals        FOR INSERT WITH CHECK (true);
CREATE POLICY "service insert trades"        ON trades         FOR INSERT WITH CHECK (true);
CREATE POLICY "service insert backtest_runs" ON backtest_runs  FOR INSERT WITH CHECK (true);
CREATE POLICY "service insert news_cache"    ON news_cache     FOR INSERT WITH CHECK (true);
CREATE POLICY "service update trades"        ON trades         FOR UPDATE USING (true);
