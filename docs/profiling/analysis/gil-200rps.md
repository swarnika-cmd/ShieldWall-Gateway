# gil-200rps

Total samples: 4912. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| event loop (MainThread) | 1 | 4585 | 93.3% |
| to_thread pool (uvloop_N) | 16 | 327 | 6.7% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 2118 | 46.2% |
| httpx/httpcore other (request build, send, response read) | 970 | 21.2% |
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 583 | 12.7% |
| httpcore: per-call import probe (current_async_library -> importlib) | 343 | 7.5% |
| Redis round trips, budget (redis.asyncio) | 317 | 6.9% |
| event loop idle (stack ends at the asyncio runner) | 74 | 1.6% |
| regex PII scans (pii.py) | 67 | 1.5% |
| JSON (de)serialisation | 54 | 1.2% |
| asyncio.to_thread dispatch/wait | 23 | 0.5% |
| tiktoken counting | 18 | 0.4% |
| DB (psycopg/db.py/auth.py) | 17 | 0.4% |
| logging | 1 | 0.0% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `run_endpoint_function (fastapi/routing.py)` | 3816 | 83.2% |
| `chat_completions (main.py)` | 3801 | 82.9% |
| `proxy_non_streaming (main.py)` | 3475 | 75.8% |
| `post (httpx/_client.py)` | 3436 | 74.9% |
| `request (httpx/_client.py)` | 3433 | 74.9% |
| `send (httpx/_client.py)` | 3358 | 73.2% |
| `_send_handling_auth (httpx/_client.py)` | 2870 | 62.6% |
| `_send_handling_redirects (httpx/_client.py)` | 2862 | 62.4% |
| `_send_single_request (httpx/_client.py)` | 2856 | 62.3% |
| `handle_async_request (httpx/_transports/default.py)` | 2801 | 61.1% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 2777 | 60.6% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py)` | 2260 | 49.3% |
| `<listcomp> (httpcore/_async/connection_pool.py)` | 1308 | 28.5% |
| `is_idle (httpcore/_async/connection.py)` | 750 | 16.4% |
| `handle_async_request (httpcore/_async/connection.py)` | 632 | 13.8% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `is_idle (httpcore/_async/http11.py:289)` | 449 | 9.8% |
| `<listcomp> (httpcore/_async/connection_pool.py:294)` | 174 | 3.8% |
| `is_idle (httpcore/_async/connection.py:195)` | 167 | 3.6% |
| `current_task (asyncio/tasks.py:38)` | 153 | 3.3% |
| `extra_attributes (anyio/abc/_sockets.py:145)` | 128 | 2.8% |
| `is_queued (httpcore/_async/connection_pool.py:40)` | 111 | 2.4% |
| `<listcomp> (httpcore/_async/connection_pool.py:302)` | 89 | 1.9% |
| `is_idle (httpcore/_async/http11.py:288)` | 84 | 1.8% |
| `current_async_library (anyio/_core/_eventloop.py:221)` | 75 | 1.6% |
| `run (asyncio/runners.py:118)` | 74 | 1.6% |
| `_raw_socket (anyio/_backends/_asyncio.py:1417)` | 71 | 1.5% |
| `extra_attributes (anyio/abc/_sockets.py:164)` | 53 | 1.2% |
| `is_closed (httpcore/_async/http11.py:292)` | 48 | 1.0% |
| `wait_for (asyncio/tasks.py:449)` | 45 | 1.0% |
| `mask (pii.py:169)` | 42 | 0.9% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 321 | 98.2% |
| other (no frame matched) | 5 | 1.5% |
| pool thread idle (waiting for work) | 1 | 0.3% |

Excluding pool-idle samples, the remaining 326 samples are the busy view:

| Bucket | % of busy samples |
|---|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 98.5% |
| other (no frame matched) | 1.5% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `enqueue_log (main.py)` | 321 | 98.2% |
| `apply_async (celery/app/task.py)` | 313 | 95.7% |
| `delay (celery/app/task.py)` | 313 | 95.7% |
| `send_task (celery/app/base.py)` | 299 | 91.4% |
| `send_task_message (celery/app/amqp.py)` | 193 | 59.0% |
| `publish (kombu/messaging.py)` | 188 | 57.5% |
| `_ensured (kombu/connection.py)` | 184 | 56.3% |
| `_publish (kombu/messaging.py)` | 179 | 54.7% |
| `basic_publish (kombu/transport/virtual/base.py)` | 148 | 45.3% |
| `_put (kombu/transport/redis.py)` | 131 | 40.1% |
| `execute_command (redis/client.py)` | 100 | 30.6% |
| `lpush (redis/commands/core.py)` | 100 | 30.6% |
| `_execute_command (redis/client.py)` | 97 | 29.7% |
| `as_task_v2 (celery/app/amqp.py)` | 49 | 15.0% |
| `wrapper (redis/utils.py)` | 44 | 13.5% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `_checkpid (redis/connection.py:3221)` | 22 | 6.7% |
| `as_dict (kombu/abstract.py:61)` | 18 | 5.5% |
| `basic_publish (kombu/transport/virtual/base.py:624)` | 13 | 4.0% |
| `anon_nodename (celery/utils/nodenames.py:66)` | 11 | 3.4% |
| `f (kombu/abstract.py:59)` | 9 | 2.8% |
| `read_response (redis/connection.py:1433)` | 8 | 2.4% |
| `__setitem__ (redis/client.py:145)` | 7 | 2.1% |
| `apply_async (celery/app/task.py:756)` | 7 | 2.1% |
| `reprstream (celery/utils/saferepr.py:227)` | 7 | 2.1% |
| `_get_filterable_args (redis/utils.py:202)` | 6 | 1.8% |
| `_saferepr (celery/utils/saferepr.py:160)` | 4 | 1.2% |
| `__get__ (kombu/utils/objects.py:39)` | 4 | 1.2% |
| `_ensured (kombu/connection.py:632)` | 4 | 1.2% |
| `enqueue_log (main.py:123)` | 4 | 1.2% |
| `_call_set_state (asyncio/futures.py:403)` | 3 | 0.9% |

