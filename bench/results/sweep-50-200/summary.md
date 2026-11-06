# Gateway overhead benchmark

Written by bench/run.sh on 2026-11-06T20:04:39.386Z.

Hardware: Apple M4 Pro (12 cores), Docker Desktop Linux VM (12 vCPUs, 7.7 GiB)

Mock upstream latency is fixed (MOCK_LATENCY_MS); overhead = gateway - direct at the same percentile.

| Rate (RPS) | Duration | Requests direct / gateway | Direct p50 / p95 / p99 (ms) | Gateway p50 / p95 / p99 (ms) | Overhead p50 / p95 / p99 (ms) | Errors direct / gateway |
|---|---|---|---|---|---|---|
| 50 | 30s | 1501 / 1501 | 201.67 / 203.72 / 204.92 | 202.94 / 205.55 / 207.71 | 1.27 / 1.84 / 2.79 | 0.00% / 0.00% |
| 200 | 30s | 6001 / 5323 | 200.86 / 202.07 / 203.25 | 1948.00 / 5352.35 / 6252.89 | 1747.14 / 5150.28 / 6049.64 | 0.00% / 3.96% |

## In-app cross-check

gateway_overhead_ms as recorded by the gateway (handler time minus upstream wait;
excludes HTTP parsing/serialisation done by uvicorn, so it is a lower bound):

```
 tenant_id  | requests | overhead_p50_ms | overhead_p99_ms | upstream_p50_ms 
------------+----------+-----------------+-----------------+-----------------
 bench-r200 |     5112 |          67.602 |         398.139 |          1814.4
 bench-r50  |     1501 |           0.481 |           1.894 |           201.8
(2 rows)

```
