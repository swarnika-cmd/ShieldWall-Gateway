# Gateway overhead benchmark

Written by bench/run.sh on 2026-11-12T19:15:19.345Z.

Hardware: Apple M4 Pro (12 cores), Docker Desktop Linux VM (12 vCPUs, 7.7 GiB)

Mock upstream latency is fixed (MOCK_LATENCY_MS); overhead = gateway - direct at the same percentile.

| Rate (RPS) | Duration | Requests direct / gateway | Direct p50 / p95 / p99 (ms) | Gateway p50 / p95 / p99 (ms) | Overhead p50 / p95 / p99 (ms) | Errors direct / gateway |
|---|---|---|---|---|---|---|
| 200 | 150s | 0 / 22720 | n/a / n/a / n/a | 1602.15 / 12926.96 / 20127.90 | n/a / n/a / n/a | n/a / 19.58% |
