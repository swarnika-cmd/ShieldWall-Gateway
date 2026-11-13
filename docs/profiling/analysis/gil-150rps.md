# gil-150rps

Total samples: 4910. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| event loop (MainThread) | 1 | 4598 | 93.6% |
| to_thread pool (uvloop_N) | 16 | 312 | 6.4% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 2649 | 57.6% |
| httpx/httpcore other (request build, send, response read) | 831 | 18.1% |
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 453 | 9.9% |
| Redis round trips, budget (redis.asyncio) | 266 | 5.8% |
| httpcore: per-call import probe (current_async_library -> importlib) | 248 | 5.4% |
| event loop idle (stack ends at the asyncio runner) | 49 | 1.1% |
| regex PII scans (pii.py) | 37 | 0.8% |
| JSON (de)serialisation | 34 | 0.7% |
| asyncio.to_thread dispatch/wait | 13 | 0.3% |
| DB (psycopg/db.py/auth.py) | 9 | 0.2% |
| tiktoken counting | 7 | 0.2% |
| logging | 2 | 0.0% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `run_endpoint_function (fastapi/routing.py)` | 4006 | 87.1% |
| `chat_completions (main.py)` | 3993 | 86.8% |
| `proxy_non_streaming (main.py)` | 3763 | 81.8% |
| `request (httpx/_client.py)` | 3731 | 81.1% |
| `post (httpx/_client.py)` | 3731 | 81.1% |
| `send (httpx/_client.py)` | 3670 | 79.8% |
| `_send_handling_auth (httpx/_client.py)` | 3151 | 68.5% |
| `_send_handling_redirects (httpx/_client.py)` | 3145 | 68.4% |
| `_send_single_request (httpx/_client.py)` | 3142 | 68.3% |
| `handle_async_request (httpx/_transports/default.py)` | 3103 | 67.5% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 3092 | 67.2% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py)` | 2737 | 59.5% |
| `<listcomp> (httpcore/_async/connection_pool.py)` | 1664 | 36.2% |
| `is_idle (httpcore/_async/connection.py)` | 1183 | 25.7% |
| `is_idle (httpcore/_async/http11.py)` | 812 | 17.7% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `is_idle (httpcore/_async/http11.py:289)` | 674 | 14.7% |
| `is_idle (httpcore/_async/connection.py:195)` | 283 | 6.2% |
| `<listcomp> (httpcore/_async/connection_pool.py:294)` | 235 | 5.1% |
| `extra_attributes (anyio/abc/_sockets.py:145)` | 152 | 3.3% |
| `current_task (asyncio/tasks.py:38)` | 139 | 3.0% |
| `is_idle (httpcore/_async/http11.py:288)` | 138 | 3.0% |
| `_raw_socket (anyio/_backends/_asyncio.py:1417)` | 88 | 1.9% |
| `current_async_library (anyio/_core/_eventloop.py:221)` | 77 | 1.7% |
| `extra_attributes (anyio/abc/_sockets.py:164)` | 62 | 1.3% |
| `<listcomp> (httpcore/_async/connection_pool.py:302)` | 57 | 1.2% |
| `run (asyncio/runners.py:118)` | 49 | 1.1% |
| `is_queued (httpcore/_async/connection_pool.py:40)` | 47 | 1.0% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py:294)` | 40 | 0.9% |
| `is_idle (httpcore/_async/connection.py:192)` | 39 | 0.8% |
| `wait_for (asyncio/tasks.py:449)` | 38 | 0.8% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 306 | 98.1% |
| other (no frame matched) | 5 | 1.6% |
| pool thread idle (waiting for work) | 1 | 0.3% |

Excluding pool-idle samples, the remaining 311 samples are the busy view:

| Bucket | % of busy samples |
|---|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 98.4% |
| other (no frame matched) | 1.6% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `enqueue_log (main.py)` | 306 | 98.1% |
| `delay (celery/app/task.py)` | 303 | 97.1% |
| `apply_async (celery/app/task.py)` | 303 | 97.1% |
| `send_task (celery/app/base.py)` | 289 | 92.6% |
| `send_task_message (celery/app/amqp.py)` | 192 | 61.5% |
| `publish (kombu/messaging.py)` | 186 | 59.6% |
| `_ensured (kombu/connection.py)` | 182 | 58.3% |
| `_publish (kombu/messaging.py)` | 179 | 57.4% |
| `basic_publish (kombu/transport/virtual/base.py)` | 166 | 53.2% |
| `_put (kombu/transport/redis.py)` | 147 | 47.1% |
| `lpush (redis/commands/core.py)` | 111 | 35.6% |
| `execute_command (redis/client.py)` | 110 | 35.3% |
| `_execute_command (redis/client.py)` | 110 | 35.3% |
| `wrapper (redis/utils.py)` | 69 | 22.1% |
| `call_with_retry (redis/retry.py)` | 41 | 13.1% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `_checkpid (redis/connection.py:3221)` | 27 | 8.7% |
| `basic_publish (kombu/transport/virtual/base.py:624)` | 17 | 5.4% |
| `connect_check_health (redis/connection.py:1035)` | 16 | 5.1% |
| `_get_filterable_args (redis/utils.py:202)` | 12 | 3.8% |
| `anon_nodename (celery/utils/nodenames.py:66)` | 9 | 2.9% |
| `iterencode (json/encoder.py:258)` | 7 | 2.2% |
| `apply_async (celery/app/task.py:756)` | 5 | 1.6% |
| `__exit__ (contextlib.py:144)` | 5 | 1.6% |
| `ensure (kombu/connection.py:557)` | 4 | 1.3% |
| `_read_from_socket (redis/_parsers/socket.py:64)` | 3 | 1.0% |
| `wrapper (redis/utils.py:258)` | 3 | 1.0% |
| `send_task_message (celery/app/amqp.py:662)` | 3 | 1.0% |
| `release (redis/connection.py:3345)` | 3 | 1.0% |
| `_to_keys (celery/utils/collections.py:398)` | 3 | 1.0% |
| `__get__ (functools.py:995)` | 3 | 1.0% |

