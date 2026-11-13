# gil-50rps

Total samples: 966. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| event loop (MainThread) | 1 | 877 | 90.8% |
| to_thread pool (uvloop_N) | 2 | 89 | 9.2% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 341 | 38.9% |
| httpx/httpcore other (request build, send, response read) | 260 | 29.6% |
| Redis round trips, budget (redis.asyncio) | 114 | 13.0% |
| httpcore: per-call import probe (current_async_library -> importlib) | 57 | 6.5% |
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 41 | 4.7% |
| JSON (de)serialisation | 16 | 1.8% |
| event loop idle (stack ends at the asyncio runner) | 16 | 1.8% |
| regex PII scans (pii.py) | 13 | 1.5% |
| asyncio.to_thread dispatch/wait | 11 | 1.3% |
| tiktoken counting | 4 | 0.5% |
| DB (psycopg/db.py/auth.py) | 4 | 0.5% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `run_endpoint_function (fastapi/routing.py)` | 473 | 53.9% |
| `chat_completions (main.py)` | 468 | 53.4% |
| `proxy_non_streaming (main.py)` | 379 | 43.2% |
| `post (httpx/_client.py)` | 361 | 41.2% |
| `request (httpx/_client.py)` | 359 | 40.9% |
| `send (httpx/_client.py)` | 310 | 35.3% |
| `_send_handling_auth (httpx/_client.py)` | 249 | 28.4% |
| `_send_single_request (httpx/_client.py)` | 248 | 28.3% |
| `_send_handling_redirects (httpx/_client.py)` | 248 | 28.3% |
| `handle_async_request (httpx/_transports/default.py)` | 218 | 24.9% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 209 | 23.8% |
| `data_received (uvicorn/protocols/http/httptools_impl.py)` | 135 | 15.4% |
| `handle_async_request (httpcore/_async/connection.py)` | 132 | 15.1% |
| `handle_async_request (httpcore/_async/http11.py)` | 123 | 14.0% |
| `__call__ (redis/commands/core.py)` | 83 | 9.5% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `data_received (uvicorn/protocols/http/httptools_impl.py:174)` | 32 | 3.6% |
| `current_task (asyncio/tasks.py:38)` | 25 | 2.9% |
| `send (anyio/_backends/_asyncio.py:1474)` | 21 | 2.4% |
| `_start_asgi_task (uvicorn/protocols/http/httptools_impl.py:309)` | 21 | 2.4% |
| `writelines (asyncio/streams.py:349)` | 19 | 2.2% |
| `run (asyncio/runners.py:118)` | 16 | 1.8% |
| `current_async_library (anyio/_core/_eventloop.py:221)` | 15 | 1.7% |
| `send (uvicorn/protocols/http/httptools_impl.py:524)` | 11 | 1.3% |
| `on_headers_complete (uvicorn/protocols/http/httptools_impl.py:249)` | 10 | 1.1% |
| `budget_keys (budget.py:94)` | 9 | 1.0% |
| `on_headers_complete (uvicorn/protocols/http/httptools_impl.py:256)` | 7 | 0.8% |
| `mask (pii.py:175)` | 7 | 0.8% |
| `on_headers_complete (uvicorn/protocols/http/httptools_impl.py:286)` | 7 | 0.8% |
| `sleep (asyncio/tasks.py:643)` | 6 | 0.7% |
| `on_headers_complete (uvicorn/protocols/http/httptools_impl.py:278)` | 6 | 0.7% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 89 | 100.0% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `delay (celery/app/task.py)` | 89 | 100.0% |
| `apply_async (celery/app/task.py)` | 89 | 100.0% |
| `send_task (celery/app/base.py)` | 89 | 100.0% |
| `enqueue_log (main.py)` | 89 | 100.0% |
| `send_task_message (celery/app/amqp.py)` | 78 | 87.6% |
| `publish (kombu/messaging.py)` | 77 | 86.5% |
| `_publish (kombu/messaging.py)` | 76 | 85.4% |
| `_ensured (kombu/connection.py)` | 76 | 85.4% |
| `basic_publish (kombu/transport/virtual/base.py)` | 71 | 79.8% |
| `_put (kombu/transport/redis.py)` | 69 | 77.5% |
| `lpush (redis/commands/core.py)` | 63 | 70.8% |
| `execute_command (redis/client.py)` | 61 | 68.5% |
| `_execute_command (redis/client.py)` | 58 | 65.2% |
| `release (redis/connection.py)` | 23 | 25.8% |
| `call_with_retry (redis/retry.py)` | 22 | 24.7% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `_checkpid (redis/connection.py:3221)` | 10 | 11.2% |
| `read_response (redis/connection.py:1433)` | 4 | 4.5% |
| `execute_command (redis/client.py:867)` | 3 | 3.4% |
| `ensure (kombu/connection.py:557)` | 3 | 3.4% |
| `release (redis/connection.py:3358)` | 2 | 2.2% |
| `wrapper (redis/utils.py:258)` | 2 | 2.2% |
| `get_observability_instance (redis/observability/providers.py:334)` | 2 | 2.2% |
| `<lambda> (redis/client.py:890)` | 2 | 2.2% |
| `_put (kombu/transport/redis.py:1704)` | 2 | 2.2% |
| `lpush (redis/commands/core.py:5110)` | 2 | 2.2% |
| `dispatch (redis/event.py:129)` | 2 | 2.2% |
| `release (redis/connection.py:3356)` | 1 | 1.1% |
| `transport (kombu/connection.py:1068)` | 1 | 1.1% |
| `send (celery/utils/dispatch/signal.py:276)` | 1 | 1.1% |
| `_read_from_socket (redis/_parsers/socket.py:68)` | 1 | 1.1% |

