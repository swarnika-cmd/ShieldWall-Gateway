# Gateway overhead benchmark

Written by bench/run.sh on 2026-11-12T19:56:58.053Z.

Hardware: Apple M4 Pro (12 cores), Docker Desktop Linux VM (12 vCPUs, 7.7 GiB)

Mock upstream latency is fixed (MOCK_LATENCY_MS); overhead = gateway - direct at the same percentile.

| Rate (RPS) | Duration | Requests direct / gateway | Direct p50 / p95 / p99 (ms) | Gateway p50 / p95 / p99 (ms) | Overhead p50 / p95 / p99 (ms) | Errors direct / gateway |
|---|---|---|---|---|---|---|
| 50 | 150s | 0 / 7500 | n/a / n/a / n/a | 203.04 / 205.62 / 207.68 | n/a / n/a / n/a | n/a / 0.00% |
