-- Tabela para armazenar resultados de backtests
CREATE TABLE IF NOT EXISTS backtest_runs (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    interval        TEXT NOT NULL,
    start_date      DATE,
    end_date        DATE,
    initial_balance NUMERIC(14,2) NOT NULL,
    final_balance   NUMERIC(14,2) NOT NULL,
    total_candles   INTEGER,
    total_signals   INTEGER,
    total_trades    INTEGER,
    wins            INTEGER,
    losses          INTEGER,
    win_rate        NUMERIC(5,2),
    profit_factor   NUMERIC(8,4),
    max_drawdown    NUMERIC(8,4),
    sharpe_ratio    NUMERIC(8,4),
    total_pnl_pct   NUMERIC(8,4),
    approved        BOOLEAN,
    notes           TEXT,
    ran_at          TIMESTAMPTZ DEFAULT NOW()
);

-- RLS: somente service_role pode inserir/ler
ALTER TABLE backtest_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service only" ON backtest_runs
    USING (auth.role() = 'service_role');
