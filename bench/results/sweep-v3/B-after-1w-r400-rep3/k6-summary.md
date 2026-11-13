# Gateway overhead benchmark

Written by bench/run.sh on 2026-11-13T03:02:05.988Z.

Hardware: Apple M4 Pro (12 cores), Docker Desktop Linux VM (12 vCPUs, 7.7 GiB)

Mock upstream latency is fixed (MOCK_LATENCY_MS); overhead = gateway - direct at the same percentile.

| Rate (RPS) | Duration | Requests direct / gateway | Direct p50 / p95 / p99 (ms) | Gateway p50 / p95 / p99 (ms) | Overhead p50 / p95 / p99 (ms) | Errors direct / gateway | Dropped iterations |
|---|---|---|---|---|---|---|---|
| 400 | 60s | 0 / 19221 | n/a / n/a / n/a | 950.01 / 9041.53 / 10545.06 | n/a / n/a / n/a | n/a / 13.21% | 4780 |
