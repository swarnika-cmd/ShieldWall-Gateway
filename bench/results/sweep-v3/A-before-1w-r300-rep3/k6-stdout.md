# Gateway overhead benchmark

Written by bench/run.sh on 2026-11-13T02:12:39.449Z.

Hardware: Apple M4 Pro (12 cores), Docker Desktop Linux VM (12 vCPUs, 7.7 GiB)

Mock upstream latency is fixed (MOCK_LATENCY_MS); overhead = gateway - direct at the same percentile.

| Rate (RPS) | Duration | Requests direct / gateway | Direct p50 / p95 / p99 (ms) | Gateway p50 / p95 / p99 (ms) | Overhead p50 / p95 / p99 (ms) | Errors direct / gateway | Dropped iterations |
|---|---|---|---|---|---|---|---|
| 300 | 60s | 0 / 17563 | n/a / n/a / n/a | 201.68 / 1308.63 / 4144.63 | n/a / n/a / n/a | n/a / 0.06% | 438 |
