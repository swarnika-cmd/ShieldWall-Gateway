# Gateway overhead benchmark

Written by bench/run.sh on 2026-11-13T02:43:30.804Z.

Hardware: Apple M4 Pro (12 cores), Docker Desktop Linux VM (12 vCPUs, 7.7 GiB)

Mock upstream latency is fixed (MOCK_LATENCY_MS); overhead = gateway - direct at the same percentile.

| Rate (RPS) | Duration | Requests direct / gateway | Direct p50 / p95 / p99 (ms) | Gateway p50 / p95 / p99 (ms) | Overhead p50 / p95 / p99 (ms) | Errors direct / gateway | Dropped iterations |
|---|---|---|---|---|---|---|---|
| 300 | 60s | 0 / 14749 | n/a / n/a / n/a | 2433.28 / 7210.46 / 9855.00 | n/a / n/a / n/a | n/a / 7.19% | 3251 |
