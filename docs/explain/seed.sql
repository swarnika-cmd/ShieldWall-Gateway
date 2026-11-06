-- 200k synthetic request_logs rows spread over the last 30 days, 20 tenants.
-- Violation mix: 20% PII_MASKED, 1% BUDGET_EXCEEDED, 0.5% UPSTREAM_ERROR, rest clean.
SELECT setseed(0.42);
INSERT INTO request_logs (request_id, tenant_id, timestamp, model, upstream_provider, latency_ms,
                          http_status, input_tokens, output_tokens, cost, violations_triggered)
SELECT 'seed_' || g,
       'tenant_' || (g % 20),
       NOW() - random() * INTERVAL '30 days',
       'gpt-4o-mini',
       'openai-compatible',
       (150 + random() * 400)::int,
       200,
       (50 + random() * 500)::int,
       (20 + random() * 300)::int,
       round((random() * 0.002)::numeric, 6),
       CASE WHEN r < 0.20 THEN 'PII_MASKED'
            WHEN r < 0.21 THEN 'BUDGET_EXCEEDED'
            WHEN r < 0.215 THEN 'UPSTREAM_ERROR'
            ELSE '' END
FROM (SELECT g, random() AS r FROM generate_series(1, 200000) AS g) AS s;
