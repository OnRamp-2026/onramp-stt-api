from __future__ import annotations

import asyncio
import os
import socket
from typing import Any, cast

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.postgres import get_session_factory
from app.queue.constants import ORCHESTRATOR_GROUP, STT_REQUEST_STREAM
from app.queue.events import decode_envelope
from app.queue.redis import bootstrap_consumer_groups, get_redis
from app.services.orchestrator import OrchestratorService
from app.storage.factory import get_storage

logger = structlog.get_logger(__name__)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    redis = get_redis()
    await bootstrap_consumer_groups(redis)
    consumer = f"orchestrator-{socket.gethostname()}-{os.getpid()}"
    service = OrchestratorService(settings, get_session_factory(), get_storage())

    while True:
        messages = cast(
            list[tuple[str, list[tuple[str, dict[str, str]]]]],
            await cast(Any, redis).xreadgroup(
                ORCHESTRATOR_GROUP,
                consumer,
                {STT_REQUEST_STREAM: ">"},
                count=1,
                block=settings.redis_stream_block_ms,
            ),
        )
        for _, entries in messages:
            for message_id, fields in entries:
                try:
                    await service.process(decode_envelope(fields))
                except Exception:
                    await logger.aexception("orchestrator_event_failed", message_id=message_id)
                    continue
                await redis.xack(STT_REQUEST_STREAM, ORCHESTRATOR_GROUP, message_id)


if __name__ == "__main__":
    asyncio.run(run())
