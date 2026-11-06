# Dashboard queries and indexes

The admin dashboard polls four endpoints every 5 seconds. This page records
what changed in v2 and what it measurably bought, using `EXPLAIN (ANALYZE, BUFFERS)`.

Reproduce with `./docs/explain/run.sh` (needs Docker). Full output:
[`docs/explain/output.txt`](explain/output.txt).

## Setup

- `postgres:16` in Docker Desktop on an Apple M4 Pro, default settings
  (`shared_buffers` 128 MB, so the whole table is in cache).
- 200,000 rows in `request_logs`, spread uniformly over 30 days, 20 tenants.
  About 6,700 rows fall into any 24-hour window.
- Violation mix: 20% `PII_MASKED`, 1% `BUDGET_EXCEEDED`, 0.5% `UPSTREAM_ERROR`, rest clean.
- Each query runs twice; the second (warm) run is reported. Single run, so
  treat differences under ~1 ms as noise.

"v1" means the original schema (`docs/explain/v1_schema.sql`) and the original
queries. "v2" means the current `schema.sql` and the queries in `admin_api.py`.

## Results

| Endpoint | v1 plan | v1 time | v1 buffers | v2 plan | v2 time | v2 buffers |
|---|---|---|---|---|---|---|
| `/api/analytics` (24h) | Bitmap index scan + heap scan, 2,874 heap pages | 5.8 ms | 2,921 | Index-only scan, 0 heap fetches | 1.9 ms | 127 |
| `/api/analytics/tenants` (24h) | Bitmap index scan + heap scan | 3.1 ms | 2,916 | Index-only scan | 1.1 ms | 122 |
| `/api/analytics/summary` | Parallel **seq scan of all 200k rows** (no window) | 14.4 ms | 3,284 | Index-only scan of the 24h window | 1.9 ms | 119 |
| `/api/security/logs` | Backward index scan on timestamp, filter dropped 342 rows | 0.35 ms | 446 | Index scan on partial index, nothing filtered | 0.15 ms | 102 |

## What actually helped, honestly

1. **Bounding `/summary` by a time window** is the biggest win, and it is a
   query change, not an index. v1 read the whole table on every poll, so its
   cost grows forever with traffic. v2 reads only the requested window.
2. **The covering index** (`(timestamp) INCLUDE (tenant_id, cost, latency_ms, ...)`)
   turns the 24h aggregates into index-only scans: buffers touched drop from
   ~2,900 to ~120 (about 24x less memory traffic). Wall-clock time drops only
   from 3 to 6 ms to 1 to 2 ms because everything is already in RAM here. The gap
   would be larger on a table that does not fit in memory.
3. **The partial index for security logs** makes almost no difference at this
   violation rate (21.5%): v1 already found 100 matching rows after reading ~440.
   It only matters when violations are rare. We kept it because it is small
   (1.9 MB vs 27 MB for the covering index) and removes the filter step.
4. **30-day windows still seq-scan** (21.7 ms in v2). The window covers the
   whole table, so a sequential scan is the right plan and the planner picks
   it. If this got slow, the fix would be a pre-aggregated daily rollup table,
   not another index.

## Costs we accepted

- The covering index is 27 MB for 200k rows (the table itself is 53 MB after
  the benchmark's UPDATE). Every insert writes into it, so write amplification
  goes up a little. v1's `(tenant_id, timestamp)` index was dropped because no
  query filtered on `tenant_id`, so the total index count per insert is unchanged.
- Index-only scans rely on the visibility map, which `VACUUM` maintains. On
  Postgres 13+ autovacuum also runs after many inserts
  (`autovacuum_vacuum_insert_threshold`), which suits this append-only table.
  If `Heap Fetches` in `EXPLAIN` starts climbing, autovacuum is falling behind.

## How to read the plans (quick guide)

- `Seq Scan`: reads every row. Fine for small tables or when most rows match.
- `Bitmap Index Scan` + `Bitmap Heap Scan`: finds matching row locations in
  the index, then visits each table page. `Heap Blocks: exact=2874` = pages read.
- `Index Only Scan` with `Heap Fetches: 0`: answered entirely from the index.
- `Rows Removed by Filter`: work done on rows that were then thrown away.
- `Buffers: shared hit=N`: number of 8 KB pages read from cache; a good
  machine-independent measure of work.
