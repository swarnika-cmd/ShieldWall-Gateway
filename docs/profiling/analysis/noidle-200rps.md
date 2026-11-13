# noidle-200rps

Total samples: 22971. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| to_thread pool (uvloop_N) | 16 | 17301 | 75.3% |
| event loop (MainThread) | 1 | 5670 | 24.7% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| pool thread idle (waiting for work) | 16636 | 96.2% |
| Celery task publish (celery/kombu, sync Redis LPUSH) | 660 | 3.8% |
| other (no frame matched) | 5 | 0.0% |

Excluding pool-idle samples, the remaining 665 samples are the busy view:

| Bucket | % of busy samples |
|---|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 99.2% |
| other (no frame matched) | 0.8% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `delay (celery/app/task.py)` | 660 | 3.8% |
| `apply_async (celery/app/task.py)` | 660 | 3.8% |
| `enqueue_log (main.py)` | 660 | 3.8% |
| `send_task (celery/app/base.py)` | 656 | 3.8% |
| `send_task_message (celery/app/amqp.py)` | 569 | 3.3% |
| `publish (kombu/messaging.py)` | 569 | 3.3% |
| `_ensured (kombu/connection.py)` | 568 | 3.3% |
| `_publish (kombu/messaging.py)` | 566 | 3.3% |
| `basic_publish (kombu/transport/virtual/base.py)` | 533 | 3.1% |
| `_put (kombu/transport/redis.py)` | 512 | 3.0% |
| `execute_command (redis/client.py)` | 481 | 2.8% |
| `lpush (redis/commands/core.py)` | 481 | 2.8% |
| `_execute_command (redis/client.py)` | 481 | 2.8% |
| `<lambda> (redis/client.py)` | 410 | 2.4% |
| `_send_command_parse_response (redis/client.py)` | 410 | 2.4% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `_worker (concurrent/futures/thread.py:81)` | 16636 | 96.2% |
| `_read_from_socket (redis/_parsers/socket.py:64)` | 248 | 1.4% |
| `send_packed_command (redis/connection.py:1349)` | 170 | 1.0% |
| `uuid4 (uuid.py:723)` | 48 | 0.3% |
| `_read_from_socket (redis/_parsers/socket.py:61)` | 24 | 0.1% |
| `dispatch (redis/event.py:129)` | 23 | 0.1% |
| `_read_from_socket (redis/_parsers/socket.py:94)` | 22 | 0.1% |
| `_ensure_connection (kombu/connection.py:467)` | 18 | 0.1% |
| `__get__ (kombu/utils/objects.py:39)` | 15 | 0.1% |
| `as_dict (kombu/abstract.py:61)` | 10 | 0.1% |
| `reprstream (celery/utils/saferepr.py:226)` | 6 | 0.0% |
| `_checkpid (redis/connection.py:3221)` | 5 | 0.0% |
| `reprstream (celery/utils/saferepr.py:235)` | 5 | 0.0% |
| `iterencode (json/encoder.py:258)` | 3 | 0.0% |
| `reprstream (celery/utils/saferepr.py:217)` | 3 | 0.0% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 2764 | 48.7% |
| httpcore: per-call import probe (current_async_library -> importlib) | 991 | 17.5% |
| httpx/httpcore other (request build, send, response read) | 915 | 16.1% |
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 462 | 8.1% |
| Redis round trips, budget (redis.asyncio) | 259 | 4.6% |
| event loop idle (stack ends at the asyncio runner) | 88 | 1.6% |
| asyncio.to_thread dispatch/wait | 61 | 1.1% |
| JSON (de)serialisation | 40 | 0.7% |
| tiktoken counting | 38 | 0.7% |
| regex PII scans (pii.py) | 24 | 0.4% |
| logging | 16 | 0.3% |
| DB (psycopg/db.py/auth.py) | 12 | 0.2% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `run_endpoint_function (fastapi/routing.py)` | 4972 | 87.7% |
| `chat_completions (main.py)` | 4948 | 87.3% |
| `proxy_non_streaming (main.py)` | 4711 | 83.1% |
| `post (httpx/_client.py)` | 4674 | 82.4% |
| `request (httpx/_client.py)` | 4672 | 82.4% |
| `send (httpx/_client.py)` | 4621 | 81.5% |
| `_send_handling_auth (httpx/_client.py)` | 4066 | 71.7% |
| `_send_handling_redirects (httpx/_client.py)` | 4063 | 71.7% |
| `_send_single_request (httpx/_client.py)` | 4057 | 71.6% |
| `handle_async_request (httpx/_transports/default.py)` | 4011 | 70.7% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 4001 | 70.6% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py)` | 3293 | 58.1% |
| `<listcomp> (httpcore/_async/connection_pool.py)` | 1319 | 23.3% |
| `has_expired (httpcore/_async/connection.py)` | 1225 | 21.6% |
| `has_expired (httpcore/_async/http11.py)` | 1216 | 21.4% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `is_socket_readable (httpcore/_utils.py:37)` | 667 | 11.8% |
| `is_idle (httpcore/_async/http11.py:289)` | 318 | 5.6% |
| `_path_stat (<frozen importlib._bootstrap_external>:147)` | 279 | 4.9% |
| `_path_importer_cache (<frozen importlib._bootstrap_external>:1434)` | 275 | 4.9% |
| `<listcomp> (httpcore/_async/connection_pool.py:302)` | 251 | 4.4% |
| `is_queued (httpcore/_async/connection_pool.py:40)` | 209 | 3.7% |
| `current_task (asyncio/tasks.py:38)` | 168 | 3.0% |
| `is_idle (httpcore/_async/connection.py:195)` | 156 | 2.8% |
| `extra_attributes (anyio/abc/_sockets.py:145)` | 115 | 2.0% |
| `<listcomp> (httpcore/_async/connection_pool.py:294)` | 95 | 1.7% |
| `current_async_library (anyio/_core/_eventloop.py:221)` | 92 | 1.6% |
| `is_queued (httpcore/_async/connection_pool.py:39)` | 88 | 1.6% |
| `run (asyncio/runners.py:118)` | 88 | 1.6% |
| `_raw_socket (anyio/_backends/_asyncio.py:1417)` | 74 | 1.3% |
| `extra_attributes (anyio/abc/_sockets.py:164)` | 53 | 0.9% |

