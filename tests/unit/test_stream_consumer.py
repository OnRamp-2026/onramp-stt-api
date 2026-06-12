from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.queue.consumer import read_new_or_reclaim_pending


@pytest.mark.asyncio
async def test_new_message_is_returned_without_reclaim() -> None:
    redis = AsyncMock()
    redis.xreadgroup.return_value = [("stream", [("1-0", {"event": "new"})])]

    messages = await read_new_or_reclaim_pending(
        redis,
        stream="stream",
        group="group",
        consumer="consumer",
        count=1,
        block_ms=100,
        reclaim_idle_ms=1000,
    )

    assert messages == [("stream", [("1-0", {"event": "new"})])]
    cast_xautoclaim: Any = redis.xautoclaim
    cast_xautoclaim.assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_pending_message_is_reclaimed() -> None:
    redis = AsyncMock()
    redis.xreadgroup.return_value = []
    redis.xautoclaim.return_value = ("0-0", [("1-0", {"event": "pending"})], [])

    messages = await read_new_or_reclaim_pending(
        redis,
        stream="stream",
        group="group",
        consumer="consumer",
        count=1,
        block_ms=100,
        reclaim_idle_ms=1000,
    )

    assert messages == [("stream", [("1-0", {"event": "pending"})])]
