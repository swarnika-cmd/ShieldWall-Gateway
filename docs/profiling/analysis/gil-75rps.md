# gil-75rps

Total samples: 3499. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| event loop (MainThread) | 1 | 3369 | 96.3% |
| to_thread pool (uvloop_N) | 14 | 130 | 3.7% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 2075 | 61.6% |
| httpx/httpcore other (request build, send, response read) | 460 | 13.7% |
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 294 | 8.7% |
| httpcore: per-call import probe (current_async_library -> importlib) | 209 | 6.2% |
| Redis round trips, budget (redis.asyncio) | 193 | 5.7% |
| JSON (de)serialisation | 39 | 1.2% |
| asyncio.to_thread dispatch/wait | 31 | 0.9% |
| event loop idle (stack ends at the asyncio runner) | 28 | 0.8% |
| DB (psycopg/db.py/auth.py) | 17 | 0.5% |
| regex PII scans (pii.py) | 14 | 0.4% |
| tiktoken counting | 9 | 0.3% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `run_endpoint_function (fastapi/routing.py)` | 2938 | 87.2% |
| `chat_completions (main.py)` | 2934 | 87.1% |
| `proxy_non_streaming (main.py)` | 2774 | 82.3% |
| `post (httpx/_client.py)` | 2752 | 81.7% |
| `request (httpx/_client.py)` | 2747 | 81.5% |
| `send (httpx/_client.py)` | 2683 | 79.6% |
| `_send_handling_auth (httpx/_client.py)` | 2349 | 69.7% |
| `_send_handling_redirects (httpx/_client.py)` | 2344 | 69.6% |
| `_send_single_request (httpx/_client.py)` | 2341 | 69.5% |
| `handle_async_request (httpx/_transports/default.py)` | 2317 | 68.8% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 2306 | 68.4% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py)` | 2183 | 64.8% |
| `<listcomp> (httpcore/_async/connection_pool.py)` | 1253 | 37.2% |
| `is_idle (httpcore/_async/connection.py)` | 944 | 28.0% |
| `has_expired (httpcore/_async/connection.py)` | 692 | 20.5% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `is_idle (httpcore/_async/http11.py:289)` | 584 | 17.3% |
| `is_idle (httpcore/_async/connection.py:195)` | 198 | 5.9% |
| `<listcomp> (httpcore/_async/connection_pool.py:294)` | 197 | 5.8% |
| `extra_attributes (anyio/abc/_sockets.py:145)` | 142 | 4.2% |
| `is_idle (httpcore/_async/http11.py:288)` | 85 | 2.5% |
| `_raw_socket (anyio/_backends/_asyncio.py:1417)` | 80 | 2.4% |
| `current_task (asyncio/tasks.py:38)` | 68 | 2.0% |
| `extra_attributes (anyio/abc/_sockets.py:164)` | 54 | 1.6% |
| `is_idle (httpcore/_async/connection.py:192)` | 44 | 1.3% |
| `current_async_library (anyio/_core/_eventloop.py:221)` | 40 | 1.2% |
| `get_extra_info (httpcore/_backends/anyio.py:92)` | 39 | 1.2% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py:294)` | 33 | 1.0% |
| `__get__ (enum.py:196)` | 29 | 0.9% |
| `run (asyncio/runners.py:118)` | 28 | 0.8% |
| `<listcomp> (httpcore/_async/connection_pool.py:302)` | 26 | 0.8% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 126 | 96.9% |
| other (no frame matched) | 4 | 3.1% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `enqueue_log (main.py)` | 126 | 96.9% |
| `apply_async (celery/app/task.py)` | 124 | 95.4% |
| `delay (celery/app/task.py)` | 124 | 95.4% |
| `send_task (celery/app/base.py)` | 119 | 91.5% |
| `send_task_message (celery/app/amqp.py)` | 79 | 60.8% |
| `_ensured (kombu/connection.py)` | 77 | 59.2% |
| `publish (kombu/messaging.py)` | 77 | 59.2% |
| `_publish (kombu/messaging.py)` | 75 | 57.7% |
| `basic_publish (kombu/transport/virtual/base.py)` | 68 | 52.3% |
| `_put (kombu/transport/redis.py)` | 59 | 45.4% |
| `lpush (redis/commands/core.py)` | 51 | 39.2% |
| `execute_command (redis/client.py)` | 51 | 39.2% |
| `_execute_command (redis/client.py)` | 50 | 38.5% |
| `call_with_retry (redis/retry.py)` | 23 | 17.7% |
| `wrapper (redis/utils.py)` | 21 | 16.2% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `_checkpid (redis/connection.py:3221)` | 9 | 6.9% |
| `basic_publish (kombu/transport/virtual/base.py:624)` | 7 | 5.4% |
| `reprstream (celery/utils/saferepr.py:219)` | 6 | 4.6% |
| `ensure (kombu/connection.py:557)` | 6 | 4.6% |
| `__setitem__ (redis/client.py:145)` | 4 | 3.1% |
| `send_task (celery/app/base.py:1214)` | 4 | 3.1% |
| `anon_nodename (celery/utils/nodenames.py:66)` | 4 | 3.1% |
| `__exit__ (contextlib.py:144)` | 3 | 2.3% |
| `_chaindict (celery/utils/saferepr.py:85)` | 3 | 2.3% |
| `_get_filterable_args (redis/utils.py:201)` | 3 | 2.3% |
| `connect_check_health (redis/connection.py:1035)` | 3 | 2.3% |
| `_execute_command (redis/client.py:889)` | 2 | 1.5% |
| `AsyncResult (celery/app/task.py:1056)` | 2 | 1.5% |
| `_read_from_socket (redis/_parsers/socket.py:64)` | 2 | 1.5% |
| `_call_set_state (asyncio/futures.py:403)` | 2 | 1.5% |

