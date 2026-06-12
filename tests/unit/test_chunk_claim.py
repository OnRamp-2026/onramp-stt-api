from datetime import UTC, datetime, timedelta

from app.db.models import ChunkStatus
from app.services.clova_worker import can_claim_chunk


def test_pending_chunk_can_be_claimed() -> None:
    now = datetime.now(UTC)

    assert can_claim_chunk(ChunkStatus.pending, None, now) is True


def test_active_processing_chunk_cannot_be_claimed() -> None:
    now = datetime.now(UTC)

    assert can_claim_chunk(ChunkStatus.processing, now + timedelta(seconds=1), now) is False


def test_expired_processing_chunk_can_be_reclaimed() -> None:
    now = datetime.now(UTC)

    assert can_claim_chunk(ChunkStatus.processing, now - timedelta(seconds=1), now) is True
