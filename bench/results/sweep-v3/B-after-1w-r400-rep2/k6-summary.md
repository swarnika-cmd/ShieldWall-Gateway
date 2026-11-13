# Gateway overhead benchmark

Written by bench/run.sh on 2026-11-13T02:47:41.685Z.

Hardware: Apple M4 Pro (12 cores), Docker Desktop Linux VM (12 vCPUs, 7.7 GiB)

Mock upstream latency is fixed (MOCK_LATENCY_MS); overhead = gateway - direct at the same percentile.

| Rate (RPS) | Duration | Requests direct / gateway | Direct p50 / p95 / p99 (ms) | Gateway p50 / p95 / p99 (ms) | Overhead p50 / p95 / p99 (ms) | Errors direct / gateway | Dropped iterations |
|---|---|---|---|---|---|---|---|
| 400 | 60s | 0 / 20938 | n/a / n/a / n/a | 787.11 / 7407.09 / 9494.90 | n/a / n/a / n/a | n/a / 12.98% | 3063 |
