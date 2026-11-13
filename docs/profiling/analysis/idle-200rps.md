# idle-200rps

Total samples: 101983. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| to_thread pool (uvloop_N) | 16 | 95984 | 94.1% |
| event loop (MainThread) | 1 | 5999 | 5.9% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| pool thread idle (waiting for work) | 93566 | 97.5% |
| Celery task publish (celery/kombu, sync Redis LPUSH) | 2414 | 2.5% |
| other (no frame matched) | 4 | 0.0% |

Excluding pool-idle samples, the remaining 2418 samples are the busy view:

| Bucket | % of busy samples |
|---|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 99.8% |
| other (no frame matched) | 0.2% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `enqueue_log (main.py)` | 2414 | 2.5% |
| `delay (celery/app/task.py)` | 2411 | 2.5% |
| `apply_async (celery/app/task.py)` | 2411 | 2.5% |
| `send_task (celery/app/base.py)` | 2405 | 2.5% |
| `send_task_message (celery/app/amqp.py)` | 2133 | 2.2% |
| `publish (kombu/messaging.py)` | 2128 | 2.2% |
| `_ensured (kombu/connection.py)` | 2126 | 2.2% |
| `_publish (kombu/messaging.py)` | 2125 | 2.2% |
| `basic_publish (kombu/transport/virtual/base.py)` | 2094 | 2.2% |
| `_put (kombu/transport/redis.py)` | 2038 | 2.1% |
| `lpush (redis/commands/core.py)` | 2015 | 2.1% |
| `execute_command (redis/client.py)` | 2014 | 2.1% |
| `_execute_command (redis/client.py)` | 2013 | 2.1% |
| `call_with_retry (redis/retry.py)` | 1684 | 1.8% |
| `<lambda> (redis/client.py)` | 1682 | 1.8% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `_worker (concurrent/futures/thread.py:81)` | 93566 | 97.5% |
| `_read_from_socket (redis/_parsers/socket.py:64)` | 956 | 1.0% |
| `send_packed_command (redis/connection.py:1349)` | 826 | 0.9% |
| `_read_from_socket (redis/_parsers/socket.py:94)` | 138 | 0.1% |
| `uuid4 (uuid.py:723)` | 128 | 0.1% |
| `wait (threading.py:327)` | 110 | 0.1% |
| `_read_from_socket (redis/_parsers/socket.py:61)` | 36 | 0.0% |
| `ensure (kombu/connection.py:557)` | 23 | 0.0% |
| `_checkpid (redis/connection.py:3221)` | 15 | 0.0% |
| `basic_publish (kombu/transport/virtual/base.py:624)` | 11 | 0.0% |
| `reprstream (celery/utils/saferepr.py:218)` | 11 | 0.0% |
| `reprstream (celery/utils/saferepr.py:286)` | 7 | 0.0% |
| `reprstream (celery/utils/saferepr.py:227)` | 5 | 0.0% |
| `__copy__ (kombu/abstract.py:71)` | 4 | 0.0% |
| `_call_set_state (asyncio/futures.py:403)` | 4 | 0.0% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 3211 | 53.5% |
| httpcore: per-call import probe (current_async_library -> importlib) | 903 | 15.1% |
| httpx/httpcore other (request build, send, response read) | 785 | 13.1% |
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 531 | 8.9% |
| Redis round trips, budget (redis.asyncio) | 368 | 6.1% |
| event loop idle (stack ends at the asyncio runner) | 59 | 1.0% |
| tiktoken counting | 45 | 0.8% |
| regex PII scans (pii.py) | 35 | 0.6% |
| JSON (de)serialisation | 30 | 0.5% |
| DB (psycopg/db.py/auth.py) | 18 | 0.3% |
| asyncio.to_thread dispatch/wait | 12 | 0.2% |
| logging | 2 | 0.0% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `run_endpoint_function (fastapi/routing.py)` | 5342 | 89.0% |
| `chat_completions (main.py)` | 5320 | 88.7% |
| `proxy_non_streaming (main.py)` | 4941 | 82.4% |
| `post (httpx/_client.py)` | 4906 | 81.8% |
| `request (httpx/_client.py)` | 4902 | 81.7% |
| `send (httpx/_client.py)` | 4821 | 80.4% |
| `_send_handling_auth (httpx/_client.py)` | 4282 | 71.4% |
| `_send_handling_redirects (httpx/_client.py)` | 4277 | 71.3% |
| `_send_single_request (httpx/_client.py)` | 4273 | 71.2% |
| `handle_async_request (httpx/_transports/default.py)` | 4240 | 70.7% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 4218 | 70.3% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py)` | 3636 | 60.6% |
| `<listcomp> (httpcore/_async/connection_pool.py)` | 1646 | 27.4% |
| `has_expired (httpcore/_async/connection.py)` | 1379 | 23.0% |
| `has_expired (httpcore/_async/http11.py)` | 1361 | 22.7% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `is_socket_readable (httpcore/_utils.py:37)` | 654 | 10.9% |
| `is_idle (httpcore/_async/http11.py:289)` | 654 | 10.9% |
| `_path_stat (<frozen importlib._bootstrap_external>:147)` | 451 | 7.5% |
| `<listcomp> (httpcore/_async/connection_pool.py:294)` | 245 | 4.1% |
| `is_idle (httpcore/_async/connection.py:195)` | 206 | 3.4% |
| `_path_importer_cache (<frozen importlib._bootstrap_external>:1434)` | 156 | 2.6% |
| `extra_attributes (anyio/abc/_sockets.py:145)` | 144 | 2.4% |
| `current_task (asyncio/tasks.py:38)` | 128 | 2.1% |
| `<listcomp> (httpcore/_async/connection_pool.py:302)` | 117 | 2.0% |
| `is_idle (httpcore/_async/http11.py:288)` | 103 | 1.7% |
| `is_queued (httpcore/_async/connection_pool.py:40)` | 100 | 1.7% |
| `_ensure_future (asyncio/tasks.py:680)` | 94 | 1.6% |
| `_raw_socket (anyio/_backends/_asyncio.py:1417)` | 87 | 1.5% |
| `current_async_library (anyio/_core/_eventloop.py:221)` | 69 | 1.2% |
| `extra_attributes (anyio/abc/_sockets.py:164)` | 62 | 1.0% |

