"""Per-project monthly budgets enforced atomically in Redis.

Flow for every request:
  1. reserve(): a Lua script checks  spent + reserved + estimate <= budget
     and, if it fits, records a "hold" for this request. Redis runs a Lua
     script as one atomic step, so two concurrent requests can never both
     see the same free budget.
  2. The request goes upstream.
  3. reconcile(): another Lua script removes the hold and adds the ACTUAL
     cost (from the provider's usage numbers) to `spent`.

Keys for one project and one calendar month (UTC), e.g. project 7, Nov 2026:
  budget:{7}:2026-11:spent        integer, micro-USD actually spent
  budget:{7}:2026-11:holds        hash    request_id -> reserved micro-USD
  budget:{7}:2026-11:hold_expiry  zset    request_id -> unix time the hold expires
The {7} part is a Redis Cluster hash tag so all three keys live on one node.

If a gateway process dies between reserve and reconcile, its hold expires
after RESERVATION_TTL_SECONDS and is swept by the next reserve() call.
"""
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import config

KEY_TTL_SECONDS = 40 * 24 * 3600  # keep a month's counters a bit past month end

RESERVE_LUA = """
local spent_key, holds_key, expiry_key = KEYS[1], KEYS[2], KEYS[3]
local budget     = tonumber(ARGV[1])
local estimate   = tonumber(ARGV[2])
local request_id = ARGV[3]
local now        = tonumber(ARGV[4])
local hold_ttl   = tonumber(ARGV[5])
local key_ttl    = tonumber(ARGV[6])

-- 1. Drop holds whose request never reconciled (crashed process).
local expired = redis.call('ZRANGEBYSCORE', expiry_key, '-inf', now)
for _, id in ipairs(expired) do
  redis.call('HDEL', holds_key, id)
end
redis.call('ZREMRANGEBYSCORE', expiry_key, '-inf', now)

-- 2. Add up what is spent and what is currently held by in-flight requests.
local spent = tonumber(redis.call('GET', spent_key) or '0')
local reserved = 0
for _, amount in ipairs(redis.call('HVALS', holds_key)) do
  reserved = reserved + tonumber(amount)
end

-- 3. Reject if this request could push us over the budget.
if spent + reserved + estimate > budget then
  return {0, spent, reserved}
end

-- 4. Otherwise hold the estimate for this request.
redis.call('HSET', holds_key, request_id, estimate)
redis.call('ZADD', expiry_key, now + hold_ttl, request_id)
redis.call('EXPIRE', holds_key, key_ttl)
redis.call('EXPIRE', expiry_key, key_ttl)
return {1, spent, reserved + estimate}
"""

RECONCILE_LUA = """
local spent_key, holds_key, expiry_key = KEYS[1], KEYS[2], KEYS[3]
local request_id = ARGV[1]
local actual     = tonumber(ARGV[2])
local key_ttl    = tonumber(ARGV[3])

redis.call('HDEL', holds_key, request_id)
redis.call('ZREM', expiry_key, request_id)
local spent = redis.call('INCRBY', spent_key, actual)
redis.call('EXPIRE', spent_key, key_ttl)
return spent
"""


class BudgetUnavailable(Exception):
    """Redis could not be reached, so the budget cannot be checked."""


@dataclass
class Reservation:
    allowed: bool
    spent_micro: int
    reserved_micro: int
    reserved_at: int  # unix time; decides which month's counters are used


def budget_keys(project_id: int, now: float = None) -> list:
    if now is None:
        now = time.time()
    month = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m")
    prefix = f"budget:{{{project_id}}}:{month}"
    return [f"{prefix}:spent", f"{prefix}:holds", f"{prefix}:hold_expiry"]


class BudgetGate:
    def __init__(self, redis_client) -> None:
        self.redis = redis_client
        # register_script uses EVALSHA, so the script body is sent only once.
        self._reserve = redis_client.register_script(RESERVE_LUA)
        self._reconcile = redis_client.register_script(RECONCILE_LUA)

    async def reserve(self, project_id: int, request_id: str, budget_micro: int,
                      estimate_micro: int) -> Reservation:
        now = int(time.time())
        try:
            allowed, spent, reserved = await self._reserve(
                keys=budget_keys(project_id, now),
                args=[budget_micro, estimate_micro, request_id, now,
                      config.RESERVATION_TTL_SECONDS, KEY_TTL_SECONDS],
            )
        except Exception as exc:  # connection refused, timeout, ...
            raise BudgetUnavailable(str(exc)) from exc
        return Reservation(bool(allowed), int(spent), int(reserved), now)

    async def reconcile(self, project_id: int, request_id: str, actual_micro: int,
                        reserved_at: float) -> int:
        # Use the month the reservation was made in, even if the request
        # finished just after midnight on the 1st.
        spent = await self._reconcile(
            keys=budget_keys(project_id, reserved_at),
            args=[request_id, actual_micro, KEY_TTL_SECONDS],
        )
        return int(spent)

    async def current(self, project_id: int) -> dict:
        spent_key, holds_key, _ = budget_keys(project_id)
        spent = int(await self.redis.get(spent_key) or 0)
        holds = await self.redis.hvals(holds_key)
        return {"spent_micro": spent, "reserved_micro": sum(int(h) for h in holds)}
