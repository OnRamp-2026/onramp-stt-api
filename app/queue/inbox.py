from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EventInbox


async def is_processed(session: AsyncSession, consumer_group: str, event_id: str) -> bool:
    return (
        await session.scalar(
            select(EventInbox.event_id).where(
                EventInbox.consumer_group == consumer_group,
                EventInbox.event_id == event_id,
            )
        )
        is not None
    )


def mark_processed(
    session: AsyncSession,
    consumer_group: str,
    event_id: str,
    result_reference: str | None = None,
) -> None:
    session.add(
        EventInbox(
            consumer_group=consumer_group,
            event_id=event_id,
            result_reference=result_reference,
        )
    )
