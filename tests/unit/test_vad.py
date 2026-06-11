from app.stt.vad import AudioFrame, SpeechSegment, iter_packed_segments, split_segment


def make_segment(start: float, frame_count: int, frame_duration: float = 1.0) -> SpeechSegment:
    return SpeechSegment(
        frames=tuple(
            AudioFrame(
                data=b"\x00\x00",
                source_start_sec=start + index * frame_duration,
                duration_sec=frame_duration,
            )
            for index in range(frame_count)
        )
    )


def test_split_segment_respects_chunk_limit() -> None:
    pieces = list(split_segment(make_segment(0, 7), max_chunk_seconds=3))

    assert [piece.duration_sec for piece in pieces] == [3, 3, 1]
    assert pieces[1].source_start_sec == 3


def test_pack_segments_accounts_for_inserted_gap() -> None:
    segments = iter([make_segment(0, 2), make_segment(10, 2), make_segment(20, 2)])

    chunks = list(iter_packed_segments(segments, max_chunk_seconds=5, gap_ms=500))

    assert [len(chunk) for chunk in chunks] == [2, 1]
