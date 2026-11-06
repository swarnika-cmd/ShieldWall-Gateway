# Gateway overhead benchmark

Written by bench/run.sh on 2026-11-06T20:07:10.223Z.

Hardware: Apple M4 Pro (12 cores), Docker Desktop Linux VM (12 vCPUs, 7.7 GiB)

Mock upstream latency is fixed (MOCK_LATENCY_MS); overhead = gateway - direct at the same percentile.

| Rate (RPS) | Duration | Requests direct / gateway | Direct p50 / p95 / p99 (ms) | Gateway p50 / p95 / p99 (ms) | Overhead p50 / p95 / p99 (ms) | Errors direct / gateway |
|---|---|---|---|---|---|---|
| 100 | 20s | 2001 / 2001 | 201.37 / 203.20 / 205.47 | 202.43 / 204.67 / 211.21 | 1.07 / 1.47 / 5.74 | 0.00% / 0.00% |
| 150 | 20s | 3001 / 3001 | 201.03 / 202.69 / 204.50 | 202.06 / 205.29 / 214.44 | 1.03 / 2.60 / 9.94 | 0.00% / 0.00% |

## In-app cross-check

gateway_overhead_ms as recorded by the gateway (handler time minus upstream wait;
excludes HTTP parsing/serialisation done by uvicorn, so it is a lower bound):

```
 tenant_id  | requests | overhead_p50_ms | overhead_p99_ms | upstream_p50_ms 
------------+----------+-----------------+-----------------+-----------------
 bench-r100 |     2001 |           0.439 |           2.545 |           201.5
 bench-r150 |     3001 |           0.342 |           3.454 |           201.4
(2 rows)

```
