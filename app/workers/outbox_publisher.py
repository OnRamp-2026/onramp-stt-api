from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.postgres import get_session_factory
from app.queue.outbox import OutboxPublisher
from app.queue.redis import get_redis


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    publisher = OutboxPublisher(get_session_factory(), get_redis())
    while True:
        published = await publisher.publish_once()
        if published == 0:
            await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(run())
