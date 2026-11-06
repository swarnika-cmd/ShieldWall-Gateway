#!/usr/bin/env bash
# Reproduces docs/db-indexing.md: seeds 200k rows into a throwaway postgres:16
# container, runs the v1 queries on the v1 schema, migrates to the v2 schema
# and runs the v2 queries. Output: docs/explain/output.txt
set -euo pipefail
cd "$(dirname "$0")/../.."
NAME=shieldwall-explain-pg
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -e POSTGRES_PASSWORD=postgres postgres:16 >/dev/null
trap 'docker rm -f "$NAME" >/dev/null' EXIT
until docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
sleep 1
psql() { docker exec -i "$NAME" psql -U postgres -v ON_ERROR_STOP=1 -q "$@"; }
run_twice() {  # first run warms the cache; keep the second
  psql < "$1" >/dev/null
  psql < "$1"
}

{
  echo "# postgres:16 in Docker, $(date -u +%Y-%m-%d)"
  psql < docs/explain/v1_schema.sql
  psql < docs/explain/seed.sql
  psql -c "VACUUM ANALYZE request_logs;"
  run_twice docs/explain/queries_v1.sql

  psql < schema.sql
  psql -c "SELECT setseed(0.7); UPDATE request_logs SET upstream_ms = latency_ms - 1, gateway_overhead_ms = 0.3 + random() * 2;"
  psql -c "VACUUM ANALYZE request_logs;"
  psql -c "SELECT pg_size_pretty(pg_relation_size('request_logs')) AS table_size, pg_size_pretty(pg_relation_size('idx_logs_time_covering')) AS covering_idx, pg_size_pretty(pg_relation_size('idx_logs_violations_time')) AS partial_idx;"
  run_twice docs/explain/queries_v2.sql
} > docs/explain/output.txt 2>&1
echo "wrote docs/explain/output.txt"
