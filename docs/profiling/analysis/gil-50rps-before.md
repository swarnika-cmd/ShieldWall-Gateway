# gil-50rps-before (P-before-1w-r50)

Total samples: 1223. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| event loop (MainThread) | 1 | 1104 | 90.3% |
| to_thread pool (uvloop_N) | 2 | 119 | 9.7% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 411 | 37.2% |
| httpx/httpcore other (request build, send, response read) | 317 | 28.7% |
| Redis round trips, budget (redis.asyncio) | 167 | 15.1% |
| httpcore: per-call import probe (current_async_library -> importlib) | 69 | 6.2% |
| JSON (de)serialisation | 37 | 3.4% |
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 35 | 3.2% |
| event loop idle (stack ends at the asyncio runner) | 23 | 2.1% |
| regex PII scans (pii.py) | 20 | 1.8% |
| tiktoken counting | 12 | 1.1% |
| DB (psycopg/db.py/auth.py) | 7 | 0.6% |
| asyncio.to_thread dispatch/wait | 6 | 0.5% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `run_endpoint_function (fastapi/routing.py)` | 611 | 55.3% |
| `chat_completions (main.py)` | 607 | 55.0% |
| `proxy_non_streaming (main.py)` | 456 | 41.3% |
| `request (httpx/_client.py)` | 434 | 39.3% |
| `post (httpx/_client.py)` | 434 | 39.3% |
| `send (httpx/_client.py)` | 375 | 34.0% |
| `_send_handling_auth (httpx/_client.py)` | 269 | 24.4% |
| `_send_handling_redirects (httpx/_client.py)` | 263 | 23.8% |
| `_send_single_request (httpx/_client.py)` | 261 | 23.6% |
| `handle_async_request (httpx/_transports/default.py)` | 228 | 20.7% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 218 | 19.7% |
| `handle_async_request (httpcore/_async/connection.py)` | 153 | 13.9% |
| `handle_async_request (httpcore/_async/http11.py)` | 142 | 12.9% |
| `__call__ (redis/commands/core.py)` | 123 | 11.1% |
| `data_received (uvicorn/protocols/http/httptools_impl.py)` | 122 | 11.1% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `current_task (asyncio/tasks.py:38)` | 41 | 3.7% |
| `data_received (uvicorn/protocols/http/httptools_impl.py:174)` | 35 | 3.2% |
| `writelines (asyncio/streams.py:349)` | 24 | 2.2% |
| `run (asyncio/runners.py:118)` | 23 | 2.1% |
| `send (anyio/_backends/_asyncio.py:1474)` | 17 | 1.5% |
| `budget_keys (budget.py:94)` | 16 | 1.4% |
| `current_async_library (anyio/_core/_eventloop.py:221)` | 14 | 1.3% |
| `mask (pii.py:175)` | 14 | 1.3% |
| `_start_asgi_task (uvicorn/protocols/http/httptools_impl.py:309)` | 12 | 1.1% |
| `on_headers_complete (uvicorn/protocols/http/httptools_impl.py:256)` | 10 | 0.9% |
| `send (uvicorn/protocols/http/httptools_impl.py:524)` | 9 | 0.8% |
| `__getitem__ (<frozen os>:676)` | 8 | 0.7% |
| `validate_python (pydantic/type_adapter.py:410)` | 8 | 0.7% |
| `_unset_keepalive_if_required (uvicorn/protocols/http/httptools_impl.py:140)` | 8 | 0.7% |
| `on_headers_complete (uvicorn/protocols/http/httptools_impl.py:249)` | 7 | 0.6% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 116 | 97.5% |
| other (no frame matched) | 3 | 2.5% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `enqueue_log (main.py)` | 116 | 97.5% |
| `apply_async (celery/app/task.py)` | 116 | 97.5% |
| `delay (celery/app/task.py)` | 116 | 97.5% |
| `send_task (celery/app/base.py)` | 114 | 95.8% |
| `send_task_message (celery/app/amqp.py)` | 102 | 85.7% |
| `publish (kombu/messaging.py)` | 101 | 84.9% |
| `_ensured (kombu/connection.py)` | 100 | 84.0% |
| `_publish (kombu/messaging.py)` | 99 | 83.2% |
| `basic_publish (kombu/transport/virtual/base.py)` | 95 | 79.8% |
| `_put (kombu/transport/redis.py)` | 89 | 74.8% |
| `execute_command (redis/client.py)` | 72 | 60.5% |
| `lpush (redis/commands/core.py)` | 72 | 60.5% |
| `_execute_command (redis/client.py)` | 69 | 58.0% |
| `call_with_retry (redis/retry.py)` | 37 | 31.1% |
| `<lambda> (redis/client.py)` | 37 | 31.1% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `_checkpid (redis/connection.py:3221)` | 7 | 5.9% |
| `read_response (redis/connection.py:1433)` | 7 | 5.9% |
| `__setitem__ (redis/client.py:145)` | 6 | 5.0% |
| `iterencode (json/encoder.py:258)` | 5 | 4.2% |
| `purge (redis/_parsers/socket.py:150)` | 4 | 3.4% |
| `purge (redis/_parsers/socket.py:151)` | 3 | 2.5% |
| `basic_publish (kombu/transport/virtual/base.py:624)` | 3 | 2.5% |
| `__contains__ (redis/client.py:133)` | 3 | 2.5% |
| `_get_filterable_args (redis/utils.py:202)` | 3 | 2.5% |
| `execute_command (redis/client.py:867)` | 3 | 2.5% |
| `_put (kombu/transport/redis.py:1704)` | 2 | 1.7% |
| `_execute_command (redis/client.py:901)` | 2 | 1.7% |
| `_call_set_state (asyncio/futures.py:403)` | 2 | 1.7% |
| `connection_kwargs (redis/connection.py:3104)` | 2 | 1.7% |
| `_execute_command (redis/client.py:897)` | 2 | 1.7% |

