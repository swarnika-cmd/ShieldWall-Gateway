# gil-100rps-10hz

Total samples: 481. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| event loop (MainThread) | 1 | 458 | 95.2% |
| to_thread pool (uvloop_N) | 12 | 23 | 4.8% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 288 | 62.9% |
| httpx/httpcore other (request build, send, response read) | 63 | 13.8% |
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 38 | 8.3% |
| httpcore: per-call import probe (current_async_library -> importlib) | 27 | 5.9% |
| Redis round trips, budget (redis.asyncio) | 25 | 5.5% |
| event loop idle (stack ends at the asyncio runner) | 7 | 1.5% |
| tiktoken counting | 3 | 0.7% |
| DB (psycopg/db.py/auth.py) | 2 | 0.4% |
| asyncio.to_thread dispatch/wait | 2 | 0.4% |
| logging | 1 | 0.2% |
| JSON (de)serialisation | 1 | 0.2% |
| regex PII scans (pii.py) | 1 | 0.2% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `run_endpoint_function (fastapi/routing.py)` | 401 | 87.6% |
| `chat_completions (main.py)` | 401 | 87.6% |
| `proxy_non_streaming (main.py)` | 380 | 83.0% |
| `request (httpx/_client.py)` | 378 | 82.5% |
| `post (httpx/_client.py)` | 378 | 82.5% |
| `send (httpx/_client.py)` | 372 | 81.2% |
| `_send_handling_auth (httpx/_client.py)` | 320 | 69.9% |
| `_send_handling_redirects (httpx/_client.py)` | 318 | 69.4% |
| `_send_single_request (httpx/_client.py)` | 317 | 69.2% |
| `handle_async_request (httpx/_transports/default.py)` | 313 | 68.3% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 312 | 68.1% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py)` | 296 | 64.6% |
| `<listcomp> (httpcore/_async/connection_pool.py)` | 191 | 41.7% |
| `is_idle (httpcore/_async/connection.py)` | 137 | 29.9% |
| `is_idle (httpcore/_async/http11.py)` | 103 | 22.5% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `is_idle (httpcore/_async/http11.py:289)` | 88 | 19.2% |
| `<listcomp> (httpcore/_async/connection_pool.py:294)` | 36 | 7.9% |
| `is_idle (httpcore/_async/connection.py:195)` | 29 | 6.3% |
| `extra_attributes (anyio/abc/_sockets.py:145)` | 18 | 3.9% |
| `is_idle (httpcore/_async/http11.py:288)` | 15 | 3.3% |
| `current_task (asyncio/tasks.py:38)` | 12 | 2.6% |
| `_raw_socket (anyio/_backends/_asyncio.py:1417)` | 10 | 2.2% |
| `extra_attributes (anyio/abc/_sockets.py:164)` | 9 | 2.0% |
| `current_async_library (anyio/_core/_eventloop.py:221)` | 7 | 1.5% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py:294)` | 7 | 1.5% |
| `run (asyncio/runners.py:118)` | 7 | 1.5% |
| `<listcomp> (httpcore/_async/connection_pool.py:302)` | 5 | 1.1% |
| `extra (anyio/_core/_typedattr.py:83)` | 5 | 1.1% |
| `get_extra_info (httpcore/_backends/anyio.py:92)` | 5 | 1.1% |
| `wait_for (asyncio/tasks.py:449)` | 5 | 1.1% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 22 | 95.7% |
| other (no frame matched) | 1 | 4.3% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `apply_async (celery/app/task.py)` | 22 | 95.7% |
| `enqueue_log (main.py)` | 22 | 95.7% |
| `send_task (celery/app/base.py)` | 22 | 95.7% |
| `delay (celery/app/task.py)` | 22 | 95.7% |
| `_ensured (kombu/connection.py)` | 11 | 47.8% |
| `send_task_message (celery/app/amqp.py)` | 11 | 47.8% |
| `publish (kombu/messaging.py)` | 11 | 47.8% |
| `_publish (kombu/messaging.py)` | 11 | 47.8% |
| `basic_publish (kombu/transport/virtual/base.py)` | 9 | 39.1% |
| `_put (kombu/transport/redis.py)` | 6 | 26.1% |
| `execute_command (redis/client.py)` | 5 | 21.7% |
| `_execute_command (redis/client.py)` | 5 | 21.7% |
| `lpush (redis/commands/core.py)` | 5 | 21.7% |
| `release (redis/connection.py)` | 3 | 13.0% |
| `as_task_v2 (celery/app/amqp.py)` | 3 | 13.0% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `basic_publish (kombu/transport/virtual/base.py:624)` | 3 | 13.0% |
| `_checkpid (redis/connection.py:3221)` | 2 | 8.7% |
| `__get__ (kombu/utils/objects.py:39)` | 2 | 8.7% |
| `send_task (celery/app/base.py:1192)` | 2 | 8.7% |
| `_to_keys (celery/utils/collections.py:392)` | 1 | 4.3% |
| `dispatch (redis/event.py:129)` | 1 | 4.3% |
| `reprstream (celery/utils/saferepr.py:227)` | 1 | 4.3% |
| `release (kombu/resource.py:128)` | 1 | 4.3% |
| `reprstream (celery/utils/saferepr.py:224)` | 1 | 4.3% |
| `release (kombu/resource.py:129)` | 1 | 4.3% |
| `__getitem__ (celery/utils/collections.py:406)` | 1 | 4.3% |
| `reprstream (celery/utils/saferepr.py:229)` | 1 | 4.3% |
| `default_channel (kombu/connection.py:1053)` | 1 | 4.3% |
| `read_response (redis/_parsers/resp3.py:52)` | 1 | 4.3% |
| `__setitem__ (redis/client.py:145)` | 1 | 4.3% |

