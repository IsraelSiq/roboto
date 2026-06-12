-- =============================================================
-- Migration 001: tabela news_impact
-- Histórico de notícias + sentiment + impacto no preço
-- Issues: #51 (cryptocurrency.cv), #52 (collector), #53 (analyzer)
-- =============================================================

CREATE TABLE IF NOT EXISTS news_impact (
    -- Identificação
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    news_id     TEXT UNIQUE NOT NULL,   -- SHA256 do título (evita duplicatas)

    -- Contexto da notícia
    symbol      TEXT NOT NULL,          -- ex: 'BNBUSDT'
    keyword     TEXT,                   -- keyword usada na busca (ex: 'bnb')
    title       TEXT NOT NULL,
    source      TEXT,                   -- ex: 'CoinDesk'
    published_at TIMESTAMPTZ,           -- quando a notícia foi publicada (ISO 8601)
    collected_at TIMESTAMPTZ DEFAULT NOW(), -- quando o bot coletou

    -- Análise de sentiment (FinBERT)
    sentiment_signal TEXT CHECK (sentiment_signal IN ('positive', 'negative', 'neutral')),
    sentiment_score  FLOAT CHECK (sentiment_score >= 0 AND sentiment_score <= 1),

    -- Preço no momento da coleta
    price_at_news FLOAT NOT NULL,

    -- Preços futuros (preenchidos pelo backfill após decorrido o tempo)
    price_1h  FLOAT,
    price_4h  FLOAT,
    price_24h FLOAT,

    -- Impacto calculado: (price_Xh - price_at_news) / price_at_news * 100
    impact_pct_1h  FLOAT,
    impact_pct_4h  FLOAT,
    impact_pct_24h FLOAT,

    -- Confirmação: True se o movimento seguiu a direção do sentiment
    direction_confirmed_1h BOOLEAN,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para consultas frequentes do NewsImpactAnalyzer
CREATE INDEX IF NOT EXISTS idx_news_impact_symbol
    ON news_impact (symbol);

CREATE INDEX IF NOT EXISTS idx_news_impact_symbol_signal_score
    ON news_impact (symbol, sentiment_signal, sentiment_score);

CREATE INDEX IF NOT EXISTS idx_news_impact_pending_backfill
    ON news_impact (symbol, collected_at)
    WHERE price_1h IS NULL;

CREATE INDEX IF NOT EXISTS idx_news_impact_collected_at
    ON news_impact (collected_at DESC);

-- Comentários de documentação
COMMENT ON TABLE news_impact IS
    'Histórico de notícias coletadas pelo Roboto com impacto no preço do ativo. '
    'Alimentado pelo NewsImpactCollector; consultado pelo NewsImpactAnalyzer.';

COMMENT ON COLUMN news_impact.news_id IS
    'Hash SHA256 dos primeiros 200 chars do título. Garante deduplicação.';

COMMENT ON COLUMN news_impact.direction_confirmed_1h IS
    'True se o preço se moveu na direção esperada pelo sentiment em 1h. '
    'Ex: positive + price_1h > price_at_news = True.';
