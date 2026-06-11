from __future__ import annotations

import time
import uuid

from redis.asyncio import Redis

ACQUIRE_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local expires_at = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local lease_id = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
if redis.call('ZCARD', key) >= limit then
  return 0
end
redis.call('ZADD', key, expires_at, lease_id)
redis.call('EXPIRE', key, math.ceil(expires_at - now))
return 1
"""


class RedisLeaseSemaphore:
    def __init__(self, redis: Redis, key: str, *, limit: int, lease_seconds: int) -> None:
        self.redis = redis
        self.key = key
        self.limit = limit
        self.lease_seconds = lease_seconds

    async def acquire(self) -> str | None:
        lease_id = uuid.uuid4().hex
        now = time.time()
        acquired = await self.redis.eval(
            ACQUIRE_SCRIPT,
            1,
            self.key,
            now,
            now + self.lease_seconds,
            self.limit,
            lease_id,
        )
        return lease_id if acquired == 1 else None

    async def release(self, lease_id: str) -> None:
        await self.redis.zrem(self.key, lease_id)
