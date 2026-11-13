# idle-100rps-nb

Total samples: 75905. py-spy rate 100 Hz, so 6000 samples = 60 thread-seconds.

| Group | Threads seen | Samples | Share of all samples |
|---|---:|---:|---:|
| to_thread pool (uvloop_N) | 16 | 71440 | 94.1% |
| event loop (MainThread) | 1 | 4360 | 5.7% |
| other ( on Unix, all file descriptors. (__doc__:-61180)) | 1 | 105 | 0.1% |

## to_thread pool (uvloop_N)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| pool thread idle (waiting for work) | 69899 | 97.8% |
| Celery task publish (celery/kombu, sync Redis LPUSH) | 1534 | 2.1% |
| other (no frame matched) | 6 | 0.0% |
| Redis round trips, budget (redis.asyncio) | 1 | 0.0% |

Excluding pool-idle samples, the remaining 1541 samples are the busy view:

| Bucket | % of busy samples |
|---|---:|
| Celery task publish (celery/kombu, sync Redis LPUSH) | 99.5% |
| other (no frame matched) | 0.4% |
| Redis round trips, budget (redis.asyncio) | 0.1% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `send_task (celery/app/base.py)` | 1522 | 2.1% |
| `delay (celery/app/task.py)` | 1521 | 2.1% |
| `apply_async (celery/app/task.py)` | 1521 | 2.1% |
| `enqueue_log (main.py)` | 1521 | 2.1% |
| `send_task_message (celery/app/amqp.py)` | 1347 | 1.9% |
| `publish (kombu/messaging.py)` | 1341 | 1.9% |
| `_ensured (kombu/connection.py)` | 1339 | 1.9% |
| `_publish (kombu/messaging.py)` | 1337 | 1.9% |
| `basic_publish (kombu/transport/virtual/base.py)` | 1325 | 1.9% |
| `_put (kombu/transport/redis.py)` | 1302 | 1.8% |
| `execute_command (redis/client.py)` | 1286 | 1.8% |
| `lpush (redis/commands/core.py)` | 1286 | 1.8% |
| `_execute_command (redis/client.py)` | 1285 | 1.8% |
| `<lambda> (redis/client.py)` | 1072 | 1.5% |
| `call_with_retry (redis/retry.py)` | 1072 | 1.5% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `_worker (concurrent/futures/thread.py:81)` | 69899 | 97.8% |
| `_read_from_socket (redis/_parsers/socket.py:64)` | 597 | 0.8% |
| `send_packed_command (redis/connection.py:1349)` | 554 | 0.8% |
| `_read_from_socket (redis/_parsers/socket.py:94)` | 92 | 0.1% |
| `uuid4 (uuid.py:723)` | 74 | 0.1% |
| `wait (threading.py:327)` | 59 | 0.1% |
| `_read_from_socket (redis/_parsers/socket.py:61)` | 30 | 0.0% |
| `reprstream (celery/utils/saferepr.py:286)` | 8 | 0.0% |
| `reprstream (celery/utils/saferepr.py:239)` | 8 | 0.0% |
| `remove (weakref.py:105)` | 6 | 0.0% |
| `reprstream (celery/utils/saferepr.py:218)` | 4 | 0.0% |
| `__setitem__ (redis/client.py:145)` | 3 | 0.0% |
| `_saferepr (celery/utils/saferepr.py:160)` | 3 | 0.0% |
| `_saferepr (celery/utils/saferepr.py:161)` | 3 | 0.0% |
| `__exit__ (contextlib.py:144)` | 3 | 0.0% |

## event loop (MainThread)

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| httpcore: connection-pool scan (_assign_requests_to_connections, is_socket_readable) | 2918 | 66.9% |
| httpx/httpcore other (request build, send, response read) | 425 | 9.7% |
| framework / residual (uvicorn, starlette, fastapi, anyio, h11, httptools) | 332 | 7.6% |
| httpcore: per-call import probe (current_async_library -> importlib) | 285 | 6.5% |
| Redis round trips, budget (redis.asyncio) | 145 | 3.3% |
| other (no frame matched) | 99 | 2.3% |
| event loop idle (stack ends at the asyncio runner) | 69 | 1.6% |
| tiktoken counting | 33 | 0.8% |
| JSON (de)serialisation | 22 | 0.5% |
| DB (psycopg/db.py/auth.py) | 10 | 0.2% |
| regex PII scans (pii.py) | 10 | 0.2% |
| asyncio.to_thread dispatch/wait | 7 | 0.2% |
| logging | 5 | 0.1% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `chat_completions (main.py)` | 3354 | 76.9% |
| `run_endpoint_function (fastapi/routing.py)` | 3343 | 76.7% |
| `request (httpx/_client.py)` | 3252 | 74.6% |
| `proxy_non_streaming (main.py)` | 3248 | 74.5% |
| `post (httpx/_client.py)` | 3243 | 74.4% |
| `send (httpx/_client.py)` | 3239 | 74.3% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py)` | 2902 | 66.6% |
| `handle_async_request (httpcore/_async/connection_pool.py)` | 2865 | 65.7% |
| `handle_async_request (httpx/_transports/default.py)` | 2861 | 65.6% |
| `_send_handling_redirects (httpx/_client.py)` | 2861 | 65.6% |
| `_send_single_request (httpx/_client.py)` | 2859 | 65.6% |
| `_send_handling_auth (httpx/_client.py)` | 2858 | 65.6% |
| `<listcomp> (httpcore/_async/connection_pool.py)` | 1625 | 37.3% |
| `is_idle (httpcore/_async/connection.py)` | 1399 | 32.1% |
| `has_expired (httpcore/_async/connection.py)` | 933 | 21.4% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `is_idle (httpcore/_async/http11.py:289)` | 689 | 15.8% |
| `<listcomp> (httpcore/_async/connection_pool.py:294)` | 599 | 13.7% |
| `is_idle (httpcore/_async/connection.py:195)` | 580 | 13.3% |
| `is_socket_readable (httpcore/_utils.py:37)` | 186 | 4.3% |
| `_path_stat (<frozen importlib._bootstrap_external>:147)` | 169 | 3.9% |
| `is_idle (httpcore/_async/connection.py:193)` | 87 | 2.0% |
| `_assign_requests_to_connections (httpcore/_async/connection_pool.py:288)` | 80 | 1.8% |
| `run (asyncio/runners.py:118)` | 69 | 1.6% |
| `has_expired (httpcore/_async/http11.py:283)` | 67 | 1.5% |
| `extra_attributes (anyio/abc/_sockets.py:164)` | 47 | 1.1% |
| `is_idle (httpcore/_async/http11.py:288)` | 46 | 1.1% |
| `(no python frames)` | 44 | 1.0% |
| `get_extra_info (httpcore/_backends/anyio.py:92)` | 43 | 1.0% |
| `<lambda> (anyio/abc/_sockets.py:152)` | 38 | 0.9% |
| `can_handle_request (httpcore/_async/connection.py:168)` | 33 | 0.8% |

## other ( on Unix, all file descriptors. (__doc__:-61180))

Buckets (first match wins, adds to 100%):

| Bucket | Samples | % of group |
|---|---:|---:|
| other (no frame matched) | 105 | 100.0% |

Top 15 frames by inclusive % (call-chain plumbing such as the ASGI wrappers, runners and thread bootstrap is skipped; it is on every stack):

| Frame | Inclusive | % of group |
|---|---:|---:|
| `(no python frames)` | 105 | 100.0% |

Top 15 frames by self % (leaf frame):

| Frame | Self | % of group |
|---|---:|---:|
| `(no python frames)` | 105 | 100.0% |

