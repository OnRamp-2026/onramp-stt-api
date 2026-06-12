from __future__ import annotations

from typing import Any, cast

from redis.asyncio import Redis

StreamEntries = list[tuple[str, dict[str, str]]]
StreamMessages = list[tuple[str, StreamEntries]]


async def read_new_or_reclaim_pending(
    redis: Redis,
    *,
    stream: str,
    group: str,
    consumer: str,
    count: int,
    block_ms: int,
    reclaim_idle_ms: int,
) -> StreamMessages:
    messages = cast(
        StreamMessages,
        await cast(Any, redis).xreadgroup(
            group,
            consumer,
            {stream: ">"},
            count=count,
            block=block_ms,
        ),
    )
    if messages:
        return messages

    claimed = cast(
        tuple[str, StreamEntries, list[str]],
        await cast(Any, redis).xautoclaim(
            stream,
            group,
            consumer,
            min_idle_time=reclaim_idle_ms,
            start_id="0-0",
            count=count,
        ),
    )
    entries = claimed[1]
    return [(stream, entries)] if entries else []
