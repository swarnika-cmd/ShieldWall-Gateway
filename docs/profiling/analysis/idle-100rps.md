# idle-100rps

Total samples: 101983. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| to_thread pool (uvloop_N) | 16 | 95984 | 94.1% |
| event loop (MainThread) | 1 | 5999 | 5.9% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| pool thread idle (waiting for work) | 94212 | 98.2% |
| Celery task publish (celery/kombu, sync Redis LPUSH) | 1769 | 1.8% |
| other (no frame matched) | 3 | 0.0% |

Excluding pool-idle samples, the remaining 1772 samples are the busy view:

| Bucket | % of busy samples |
|---|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 99.8% |
| other (no frame matched) | 0.2% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `delay (celery/app/task.py)` | 1769 | 1.8% |
| `enqueue_log (main.py)` | 1769 | 1.8% |
| `apply_async (celery/app/task.py)` | 1769 | 1.8% |
| `send_task (celery/app/base.py)` | 1762 | 1.8% |
| `publish (kombu/messaging.py)` | 1632 | 1.7% |
| `send_task_message (celery/app/amqp.py)` | 1632 | 1.7% |
| `_publish (kombu/messaging.py)` | 1628 | 1.7% |
| `_ensured (kombu/connection.py)` | 1628 | 1.7% |
| `basic_publish (kombu/transport/virtual/base.py)` | 1610 | 1.7% |
| `_put (kombu/transport/redis.py)` | 1567 | 1.6% |
| `_execute_command (redis/client.py)` | 1541 | 1.6% |
| `lpush (redis/commands/core.py)` | 1541 | 1.6% |
| `execute_command (redis/client.py)` | 1541 | 1.6% |
| `<lambda> (redis/client.py)` | 1300 | 1.4% |
| `_send_command_parse_response (redis/client.py)` | 1300 | 1.4% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `_worker (concurrent/futures/thread.py:81)` | 94212 | 98.2% |
| `_read_from_socket (redis/_parsers/socket.py:64)` | 759 | 0.8% |
| `send_packed_command (redis/connection.py:1349)` | 590 | 0.6% |
| `_read_from_socket (redis/_parsers/socket.py:94)` | 106 | 0.1% |
| `uuid4 (uuid.py:723)` | 79 | 0.1% |
| `wait (threading.py:327)` | 28 | 0.0% |
| `_read_from_socket (redis/_parsers/socket.py:61)` | 25 | 0.0% |
| `_checkpid (redis/connection.py:3221)` | 17 | 0.0% |
| `__exit__ (contextlib.py:144)` | 16 | 0.0% |
| `basic_publish (kombu/transport/virtual/base.py:624)` | 10 | 0.0% |
| `anon_nodename (celery/utils/nodenames.py:66)` | 5 | 0.0% |
| `__setitem__ (redis/client.py:145)` | 5 | 0.0% |
| `iterencode (json/encoder.py:258)` | 4 | 0.0% |
| `remove (weakref.py:105)` | 4 | 0.0% |
| `__getitem__ (celery/utils/collections.py:406)` | 3 | 0.0% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 3905 | 65.1% |
| httpcore: per-call import probe (current_async_library -> importlib) | 678 | 11.3% |
| httpx/httpcore other (request build, send, response read) | 652 | 10.9% |
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 315 | 5.3% |
| Redis round trips, budget (redis.asyncio) | 228 | 3.8% |
| event loop idle (stack ends at the asyncio runner) | 69 | 1.2% |
| JSON (de)serialisation | 59 | 1.0% |
| tiktoken counting | 32 | 0.5% |
| regex PII scans (pii.py) | 23 | 0.4% |
| asyncio.to_thread dispatch/wait | 22 | 0.4% |
| DB (psycopg/db.py/auth.py) | 15 | 0.3% |
| logging | 1 | 0.0% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `run_endpoint_function (fastapi/routing.py)` | 5491 | 91.5% |
| `chat_completions (main.py)` | 5482 | 91.4% |
| `proxy_non_streaming (main.py)` | 5278 | 88.0% |
| `post (httpx/_client.py)` | 5248 | 87.5% |
| `request (httpx/_client.py)` | 5246 | 87.4% |
| `send (httpx/_client.py)` | 5163 | 86.1% |
| `_send_handling_auth (httpx/_client.py)` | 4519 | 75.3% |
| `_send_handling_redirects (httpx/_client.py)` | 4513 | 75.2% |
| `_send_single_request (httpx/_client.py)` | 4511 | 75.2% |
| `handle_async_request (httpx/_transports/default.py)` | 4477 | 74.6% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 4461 | 74.4% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py)` | 4198 | 70.0% |
| `<listcomp> (httpcore/_async/connection_pool.py)` | 1934 | 32.2% |
| `has_expired (httpcore/_async/connection.py)` | 1781 | 29.7% |
| `has_expired (httpcore/_async/http11.py)` | 1763 | 29.4% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `is_idle (httpcore/_async/http11.py:289)` | 871 | 14.5% |
| `is_socket_readable (httpcore/_utils.py:37)` | 864 | 14.4% |
| `<listcomp> (httpcore/_async/connection_pool.py:294)` | 344 | 5.7% |
| `_path_stat (<frozen importlib._bootstrap_external>:147)` | 309 | 5.2% |
| `is_idle (httpcore/_async/connection.py:195)` | 288 | 4.8% |
| `extra_attributes (anyio/abc/_sockets.py:145)` | 207 | 3.5% |
| `is_idle (httpcore/_async/http11.py:288)` | 147 | 2.5% |
| `_path_importer_cache (<frozen importlib._bootstrap_external>:1434)` | 140 | 2.3% |
| `current_task (asyncio/tasks.py:38)` | 114 | 1.9% |
| `_raw_socket (anyio/_backends/_asyncio.py:1417)` | 111 | 1.9% |
| `extra_attributes (anyio/abc/_sockets.py:164)` | 91 | 1.5% |
| `run (asyncio/runners.py:118)` | 69 | 1.2% |
| `current_async_library (anyio/_core/_eventloop.py:221)` | 64 | 1.1% |
| `<listcomp> (httpcore/_async/connection_pool.py:302)` | 49 | 0.8% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py:294)` | 45 | 0.8% |

