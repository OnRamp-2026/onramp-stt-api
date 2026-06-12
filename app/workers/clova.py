from __future__ import annotations

import asyncio
import os
import socket

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.postgres import get_session_factory
from app.queue.constants import CLOVA_WORKER_GROUP, STT_CHUNK_STREAM
from app.queue.consumer import read_new_or_reclaim_pending
from app.queue.events import decode_envelope
from app.queue.redis import bootstrap_consumer_groups, get_redis
from app.queue.semaphore import RedisLeaseSemaphore
from app.services.clova_worker import ClovaChunkService
from app.storage.factory import get_storage
from app.stt.providers.clova import ClovaSpeechProvider

logger = structlog.get_logger(__name__)


async def renew_lease(
    semaphore: RedisLeaseSemaphore,
    lease_id: str,
    interval_seconds: float,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        if not await semaphore.renew(lease_id):
            await logger.awarning("clova_semaphore_lease_lost", lease_id=lease_id)
            return


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    redis = get_redis()
    await bootstrap_consumer_groups(redis)
    consumer = f"clova-{socket.gethostname()}-{os.getpid()}"
    semaphore = RedisLeaseSemaphore(
        redis,
        "onramp:stt:clova:permits",
        limit=settings.clova_max_concurrent_jobs,
        lease_seconds=settings.clova_semaphore_lease_sec,
    )
    service = ClovaChunkService(
        settings,
        get_session_factory(),
        get_storage(),
        ClovaSpeechProvider(settings),
    )

    while True:
        messages = await read_new_or_reclaim_pending(
            redis,
            stream=STT_CHUNK_STREAM,
            group=CLOVA_WORKER_GROUP,
            consumer=consumer,
            count=1,
            block_ms=settings.redis_stream_block_ms,
            reclaim_idle_ms=settings.redis_pending_reclaim_idle_ms,
        )
        for _, entries in messages:
            for message_id, fields in entries:
                lease_id = None
                while lease_id is None:
                    lease_id = await semaphore.acquire()
                    if lease_id is not None:
                        break
                    await asyncio.sleep(1)
                heartbeat = asyncio.create_task(
                    renew_lease(
                        semaphore,
                        lease_id,
                        max(1.0, settings.clova_semaphore_lease_sec / 3),
                    )
                )
                try:
                    await service.process(decode_envelope(fields), consumer)
                except Exception:
                    await logger.aexception("clova_event_failed", message_id=message_id)
                    continue
                finally:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)
                    await semaphore.release(lease_id)
                await redis.xack(STT_CHUNK_STREAM, CLOVA_WORKER_GROUP, message_id)


if __name__ == "__main__":
    asyncio.run(run())
