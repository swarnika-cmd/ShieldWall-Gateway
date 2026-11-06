-- Dashboard queries exactly as v1 ran them (window = 24 hours).
\echo '=== v1 /api/analytics (24h) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms), 0.0), COALESCE(SUM(cost), 0.0),
       COALESCE(AVG(faithfulness), 0.0)
FROM request_logs WHERE timestamp >= NOW() - CAST('24 hours' AS INTERVAL);

\echo '=== v1 /api/analytics/tenants (24h) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT tenant_id, COALESCE(SUM(cost), 0.0) AS total_cost FROM request_logs
WHERE timestamp >= NOW() - CAST('24 hours' AS INTERVAL) GROUP BY tenant_id ORDER BY total_cost DESC;

\echo '=== v1 /api/analytics/summary (no window: whole table) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT COALESCE(SUM(cost), 0.0),
       COUNT(*) FILTER (WHERE violations_triggered LIKE '%BUDGET_EXCEEDED%' OR violations_triggered LIKE '%MALICIOUS_INJECTION%'),
       COALESCE(AVG(latency_ms), 0.0)
FROM request_logs;

\echo '=== v1 /api/security/logs (no window) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT request_id, tenant_id, EXTRACT(EPOCH FROM timestamp), model, latency_ms, http_status, violations_triggered
FROM request_logs WHERE violations_triggered IS NOT NULL AND violations_triggered != ''
ORDER BY timestamp DESC LIMIT 100;
