# gil-50rps-after (P-after-1w-r50)

Total samples: 1341. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| event loop (MainThread) | 1 | 1212 | 90.4% |
| to_thread pool (uvloop_N) | 2 | 129 | 9.6% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 518 | 42.7% |
| httpx/httpcore other (request build, send, response read) | 320 | 26.4% |
| Redis round trips, budget (redis.asyncio) | 173 | 14.3% |
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 49 | 4.0% |
| event loop idle (stack ends at the asyncio runner) | 38 | 3.1% |
| JSON (de)serialisation | 35 | 2.9% |
| regex PII scans (pii.py) | 26 | 2.1% |
| asyncio.to_thread dispatch/wait | 17 | 1.4% |
| DB (psycopg/db.py/auth.py) | 17 | 1.4% |
| httpcore: per-call import probe (current_async_library -> importlib) | 11 | 0.9% |
| tiktoken counting | 8 | 0.7% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `run_endpoint_function (fastapi/routing.py)` | 596 | 49.2% |
| `chat_completions (main.py)` | 592 | 48.8% |
| `proxy_non_streaming (main.py)` | 413 | 34.1% |
| `post (httpx/_client.py)` | 390 | 32.2% |
| `request (httpx/_client.py)` | 390 | 32.2% |
| `send (httpx/_client.py)` | 331 | 27.3% |
| `_send_handling_auth (httpx/_client.py)` | 245 | 20.2% |
| `_send_handling_redirects (httpx/_client.py)` | 242 | 20.0% |
| `_send_single_request (httpx/_client.py)` | 241 | 19.9% |
| `handle_async_request (httpx/_transports/default.py)` | 219 | 18.1% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 204 | 16.8% |
| `handle_async_request (httpcore/_async/connection.py)` | 159 | 13.1% |
| `data_received (uvicorn/protocols/http/httptools_impl.py)` | 157 | 13.0% |
| `handle_async_request (httpcore/_async/http11.py)` | 152 | 12.5% |
| `__call__ (redis/commands/core.py)` | 133 | 11.0% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `current_task (asyncio/tasks.py:38)` | 46 | 3.8% |
| `run (asyncio/runners.py:118)` | 38 | 3.1% |
| `data_received (uvicorn/protocols/http/httptools_impl.py:174)` | 27 | 2.2% |
| `on_headers_complete (uvicorn/protocols/http/httptools_impl.py:249)` | 18 | 1.5% |
| `writelines (asyncio/streams.py:349)` | 18 | 1.5% |
| `send (anyio/_backends/_asyncio.py:1474)` | 17 | 1.4% |
| `mask (pii.py:175)` | 16 | 1.3% |
| `budget_keys (budget.py:94)` | 15 | 1.2% |
| `_start_asgi_task (uvicorn/protocols/http/httptools_impl.py:309)` | 13 | 1.1% |
| `on_headers_complete (uvicorn/protocols/http/httptools_impl.py:256)` | 12 | 1.0% |
| `validate_python (pydantic/type_adapter.py:410)` | 11 | 0.9% |
| `data_received (anyio/_backends/_asyncio.py:1360)` | 8 | 0.7% |
| `timeout (asyncio/timeouts.py:145)` | 8 | 0.7% |
| `_unset_keepalive_if_required (uvicorn/protocols/http/httptools_impl.py:140)` | 8 | 0.7% |
| `validate (h11/_util.py:87)` | 8 | 0.7% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 128 | 99.2% |
| other (no frame matched) | 1 | 0.8% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `enqueue_log (main.py)` | 128 | 99.2% |
| `delay (celery/app/task.py)` | 128 | 99.2% |
| `apply_async (celery/app/task.py)` | 128 | 99.2% |
| `send_task (celery/app/base.py)` | 128 | 99.2% |
| `send_task_message (celery/app/amqp.py)` | 110 | 85.3% |
| `publish (kombu/messaging.py)` | 109 | 84.5% |
| `_publish (kombu/messaging.py)` | 108 | 83.7% |
| `_ensured (kombu/connection.py)` | 108 | 83.7% |
| `basic_publish (kombu/transport/virtual/base.py)` | 106 | 82.2% |
| `_put (kombu/transport/redis.py)` | 96 | 74.4% |
| `lpush (redis/commands/core.py)` | 83 | 64.3% |
| `execute_command (redis/client.py)` | 82 | 63.6% |
| `_execute_command (redis/client.py)` | 80 | 62.0% |
| `<lambda> (redis/client.py)` | 29 | 22.5% |
| `call_with_retry (redis/retry.py)` | 29 | 22.5% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `_checkpid (redis/connection.py:3221)` | 12 | 9.3% |
| `basic_publish (kombu/transport/virtual/base.py:624)` | 9 | 7.0% |
| `iterencode (json/encoder.py:258)` | 7 | 5.4% |
| `read_response (redis/connection.py:1433)` | 6 | 4.7% |
| `_execute_command (redis/client.py:897)` | 5 | 3.9% |
| `should_reconnect (redis/connection.py:1311)` | 4 | 3.1% |
| `_get_filterable_args (redis/utils.py:201)` | 3 | 2.3% |
| `_execute_command (redis/client.py:889)` | 3 | 2.3% |
| `readline (redis/_parsers/socket.py:118)` | 3 | 2.3% |
| `listen (redis/event.py:369)` | 2 | 1.6% |
| `release (redis/connection.py:3365)` | 2 | 1.6% |
| `unread_bytes (redis/_parsers/socket.py:41)` | 2 | 1.6% |
| `get_observability_instance (redis/observability/providers.py:334)` | 2 | 1.6% |
| `get_provider_manager (redis/observability/providers.py:260)` | 2 | 1.6% |
| `_read_response (redis/_parsers/resp3.py:65)` | 2 | 1.6% |

