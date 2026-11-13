# Gateway overhead benchmark

Written by bench/run.sh on 2026-11-13T02:06:28.064Z.

Hardware: Apple M4 Pro (12 cores), Docker Desktop Linux VM (12 vCPUs, 7.7 GiB)

Mock upstream latency is fixed (MOCK_LATENCY_MS); overhead = gateway - direct at the same percentile.

| Rate (RPS) | Duration | Requests direct / gateway | Direct p50 / p95 / p99 (ms) | Gateway p50 / p95 / p99 (ms) | Overhead p50 / p95 / p99 (ms) | Errors direct / gateway | Dropped iterations |
|---|---|---|---|---|---|---|---|
| 250 | 60s | 0 / 15001 | n/a / n/a / n/a | 201.23 / 202.44 / 203.83 | n/a / n/a / n/a | n/a / 0.00% | 0 |
