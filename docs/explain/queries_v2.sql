-- Dashboard queries as v2 runs them (admin_api.py), window = 24 hours.
\echo '=== v2 /api/analytics (24h) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT COUNT(*), COALESCE(SUM(cost), 0), percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),
       AVG(relevance_score)
FROM request_logs WHERE timestamp >= NOW() - INTERVAL '24 hours';

\echo '=== v2 /api/analytics/tenants (24h) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT tenant_id, SUM(cost) AS total_cost FROM request_logs
WHERE timestamp >= NOW() - INTERVAL '24 hours' GROUP BY tenant_id ORDER BY total_cost DESC;

\echo '=== v2 /api/analytics/tenants (30d) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT tenant_id, SUM(cost) AS total_cost FROM request_logs
WHERE timestamp >= NOW() - INTERVAL '30 days' GROUP BY tenant_id ORDER BY total_cost DESC;

\echo '=== v2 /api/analytics/summary (24h) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT COUNT(*), COALESCE(SUM(cost), 0),
       COUNT(*) FILTER (WHERE violations_triggered = 'BUDGET_EXCEEDED'),
       percentile_cont(0.5)  WITHIN GROUP (ORDER BY gateway_overhead_ms) FILTER (WHERE upstream_ms IS NOT NULL),
       percentile_cont(0.99) WITHIN GROUP (ORDER BY gateway_overhead_ms) FILTER (WHERE upstream_ms IS NOT NULL),
       percentile_cont(0.5)  WITHIN GROUP (ORDER BY upstream_ms)
FROM request_logs WHERE timestamp >= NOW() - INTERVAL '24 hours';

\echo '=== v2 /api/security/logs (24h) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT request_id, tenant_id, EXTRACT(EPOCH FROM timestamp), model, latency_ms, http_status,
       violations_triggered, pii_entities
FROM request_logs
WHERE violations_triggered IS NOT NULL AND violations_triggered <> ''
  AND timestamp >= NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC LIMIT 100;
