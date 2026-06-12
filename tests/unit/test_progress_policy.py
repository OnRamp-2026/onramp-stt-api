from datetime import UTC, datetime, timedelta

from app.services.clova_worker import should_emit_progress


def test_status_change_always_emits() -> None:
    now = datetime.now(UTC)

    assert (
        should_emit_progress(
            status_changed=True,
            previous_ratio=0.1,
            current_ratio=0.1,
            last_emitted_at=now,
            now=now,
        )
        is True
    )


def test_large_ratio_increase_emits() -> None:
    now = datetime.now(UTC)

    assert (
        should_emit_progress(
            status_changed=False,
            previous_ratio=0.10,
            current_ratio=0.16,
            last_emitted_at=now,
            now=now,
        )
        is True
    )


def test_first_progress_always_emits() -> None:
    now = datetime.now(UTC)

    assert (
        should_emit_progress(
            status_changed=False,
            previous_ratio=0.0,
            current_ratio=0.01,
            last_emitted_at=None,
            now=now,
        )
        is True
    )


def test_small_ratio_increase_within_interval_does_not_emit() -> None:
    now = datetime.now(UTC)
    last_emitted_at = now - timedelta(seconds=5)

    assert (
        should_emit_progress(
            status_changed=False,
            previous_ratio=0.10,
            current_ratio=0.12,
            last_emitted_at=last_emitted_at,
            now=now,
        )
        is False
    )


def test_small_ratio_increase_after_interval_emits() -> None:
    now = datetime.now(UTC)
    last_emitted_at = now - timedelta(seconds=11)

    assert (
        should_emit_progress(
            status_changed=False,
            previous_ratio=0.10,
            current_ratio=0.12,
            last_emitted_at=last_emitted_at,
            now=now,
        )
        is True
    )
