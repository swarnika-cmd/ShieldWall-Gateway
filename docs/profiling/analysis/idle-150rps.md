# idle-150rps

Total samples: 101983. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| to_thread pool (uvloop_N) | 16 | 95984 | 94.1% |
| event loop (MainThread) | 1 | 5999 | 5.9% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| pool thread idle (waiting for work) | 93499 | 97.4% |
| Celery task publish (celery/kombu, sync Redis LPUSH) | 2479 | 2.6% |
| other (no frame matched) | 6 | 0.0% |

Excluding pool-idle samples, the remaining 2485 samples are the busy view:

| Bucket | % of busy samples |
|---|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 99.8% |
| other (no frame matched) | 0.2% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `enqueue_log (main.py)` | 2479 | 2.6% |
| `apply_async (celery/app/task.py)` | 2474 | 2.6% |
| `delay (celery/app/task.py)` | 2474 | 2.6% |
| `send_task (celery/app/base.py)` | 2467 | 2.6% |
| `send_task_message (celery/app/amqp.py)` | 2098 | 2.2% |
| `publish (kombu/messaging.py)` | 2094 | 2.2% |
| `_ensured (kombu/connection.py)` | 2090 | 2.2% |
| `_publish (kombu/messaging.py)` | 2087 | 2.2% |
| `basic_publish (kombu/transport/virtual/base.py)` | 2081 | 2.2% |
| `_put (kombu/transport/redis.py)` | 2035 | 2.1% |
| `lpush (redis/commands/core.py)` | 2007 | 2.1% |
| `execute_command (redis/client.py)` | 2005 | 2.1% |
| `_execute_command (redis/client.py)` | 2003 | 2.1% |
| `call_with_retry (redis/retry.py)` | 1666 | 1.7% |
| `<lambda> (redis/client.py)` | 1666 | 1.7% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `_worker (concurrent/futures/thread.py:81)` | 93498 | 97.4% |
| `_read_from_socket (redis/_parsers/socket.py:64)` | 909 | 0.9% |
| `send_packed_command (redis/connection.py:1349)` | 851 | 0.9% |
| `_read_from_socket (redis/_parsers/socket.py:94)` | 140 | 0.1% |
| `uuid4 (uuid.py:723)` | 118 | 0.1% |
| `wait (threading.py:327)` | 108 | 0.1% |
| `__enter__ (threading.py:272)` | 106 | 0.1% |
| `_read_from_socket (redis/_parsers/socket.py:61)` | 36 | 0.0% |
| `_checkpid (redis/connection.py:3221)` | 14 | 0.0% |
| `anon_nodename (celery/utils/nodenames.py:66)` | 9 | 0.0% |
| `basic_publish (kombu/transport/virtual/base.py:624)` | 8 | 0.0% |
| `__setitem__ (redis/client.py:145)` | 8 | 0.0% |
| `_get (queue.py:254)` | 8 | 0.0% |
| `__getitem__ (celery/utils/collections.py:406)` | 6 | 0.0% |
| `_get_filterable_args (redis/utils.py:202)` | 6 | 0.0% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 3532 | 58.9% |
| httpx/httpcore other (request build, send, response read) | 826 | 13.8% |
| httpcore: per-call import probe (current_async_library -> importlib) | 789 | 13.2% |
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 402 | 6.7% |
| Redis round trips, budget (redis.asyncio) | 235 | 3.9% |
| event loop idle (stack ends at the asyncio runner) | 93 | 1.6% |
| tiktoken counting | 31 | 0.5% |
| JSON (de)serialisation | 30 | 0.5% |
| regex PII scans (pii.py) | 27 | 0.5% |
| asyncio.to_thread dispatch/wait | 18 | 0.3% |
| DB (psycopg/db.py/auth.py) | 14 | 0.2% |
| logging | 2 | 0.0% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `run_endpoint_function (fastapi/routing.py)` | 5414 | 90.2% |
| `chat_completions (main.py)` | 5410 | 90.2% |
| `proxy_non_streaming (main.py)` | 5180 | 86.3% |
| `post (httpx/_client.py)` | 5155 | 85.9% |
| `request (httpx/_client.py)` | 5151 | 85.9% |
| `send (httpx/_client.py)` | 5083 | 84.7% |
| `_send_handling_auth (httpx/_client.py)` | 4420 | 73.7% |
| `_send_handling_redirects (httpx/_client.py)` | 4412 | 73.5% |
| `_send_single_request (httpx/_client.py)` | 4409 | 73.5% |
| `handle_async_request (httpx/_transports/default.py)` | 4371 | 72.9% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 4343 | 72.4% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py)` | 3901 | 65.0% |
| `<listcomp> (httpcore/_async/connection_pool.py)` | 1834 | 30.6% |
| `has_expired (httpcore/_async/connection.py)` | 1501 | 25.0% |
| `has_expired (httpcore/_async/http11.py)` | 1489 | 24.8% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `is_idle (httpcore/_async/http11.py:289)` | 730 | 12.2% |
| `is_socket_readable (httpcore/_utils.py:37)` | 690 | 11.5% |
| `_path_stat (<frozen importlib._bootstrap_external>:147)` | 402 | 6.7% |
| `<listcomp> (httpcore/_async/connection_pool.py:294)` | 319 | 5.3% |
| `is_idle (httpcore/_async/connection.py:195)` | 264 | 4.4% |
| `extra_attributes (anyio/abc/_sockets.py:145)` | 170 | 2.8% |
| `is_idle (httpcore/_async/http11.py:288)` | 129 | 2.2% |
| `current_task (asyncio/tasks.py:38)` | 124 | 2.1% |
| `_path_importer_cache (<frozen importlib._bootstrap_external>:1434)` | 121 | 2.0% |
| `_raw_socket (anyio/_backends/_asyncio.py:1417)` | 103 | 1.7% |
| `run (asyncio/runners.py:118)` | 93 | 1.6% |
| `current_async_library (anyio/_core/_eventloop.py:221)` | 81 | 1.4% |
| `<listcomp> (httpcore/_async/connection_pool.py:302)` | 73 | 1.2% |
| `extra_attributes (anyio/abc/_sockets.py:164)` | 72 | 1.2% |
| `is_queued (httpcore/_async/connection_pool.py:40)` | 64 | 1.1% |

