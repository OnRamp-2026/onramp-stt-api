from redis.asyncio import Redis

from app.core.config import get_settings
from app.queue.constants import STREAM_GROUPS

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def bootstrap_consumer_groups(client: Redis) -> None:
    for stream, group in STREAM_GROUPS.items():
        try:
            await client.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise


async def check_redis() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None
