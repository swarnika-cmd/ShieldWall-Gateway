-- ShieldWall schema. Safe to run many times (every statement is idempotent).
-- Applied by the API at startup and by scripts/create_project.py.

-- Only one process migrates at a time; the lock is released at commit.
SELECT pg_advisory_xact_lock(724100);

-- One row per client application. Only the SHA-256 of the API key is stored.
CREATE TABLE IF NOT EXISTS projects (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    api_key_hash CHAR(64) UNIQUE NOT NULL,
    monthly_budget_usd NUMERIC(12, 6) NOT NULL CHECK (monthly_budget_usd >= 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- One row per proxied request. Never contains prompt/response text or raw PII.
CREATE TABLE IF NOT EXISTS request_logs (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(64) UNIQUE NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,              -- project name
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    model VARCHAR(64) NOT NULL,
    upstream_provider VARCHAR(64) NOT NULL,
    latency_ms INTEGER NOT NULL,                 -- total time inside the gateway handler
    http_status INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost NUMERIC(10, 6) NOT NULL,                -- USD
    violations_triggered VARCHAR(256)
);

-- v2 columns (ADD COLUMN IF NOT EXISTS keeps old databases working)
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS upstream_ms REAL;          -- wait for the provider
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS gateway_overhead_ms REAL;  -- time in gateway code
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS pii_entities JSONB;   -- e.g. {"EMAIL": 2}
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS relevance_score NUMERIC(4, 3);

-- v1 stored a cross-encoder score under the misleading name "faithfulness".
-- Keep the old context_relevance values under the new name, drop the rest.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'request_logs' AND column_name = 'context_relevance') THEN
        UPDATE request_logs SET relevance_score = context_relevance
        WHERE relevance_score IS NULL AND context_relevance IS NOT NULL;
        ALTER TABLE request_logs DROP COLUMN context_relevance;
    END IF;
END $$;
ALTER TABLE request_logs DROP COLUMN IF EXISTS faithfulness;

-- Dashboard indexes
CREATE INDEX IF NOT EXISTS idx_tenant_timestamp ON request_logs(tenant_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_timestamp_latency ON request_logs(timestamp DESC, latency_ms);
