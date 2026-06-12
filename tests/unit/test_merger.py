from app.stt.merger import map_chunk_time, merge_chunk_segments, render_plain_text


def test_merge_maps_vad_chunk_time_to_source_time() -> None:
    segments = merge_chunk_segments(
        [
            (
                [
                    {
                        "chunk_start_sec": 0.0,
                        "chunk_end_sec": 2.0,
                        "source_start_sec": 10.0,
                        "source_end_sec": 12.0,
                    },
                    {
                        "chunk_start_sec": 2.25,
                        "chunk_end_sec": 4.25,
                        "source_start_sec": 20.0,
                        "source_end_sec": 22.0,
                    },
                ],
                [
                    {
                        "start_time_sec": 0.5,
                        "end_time_sec": 1.5,
                        "text": "첫 번째 발화",
                        "speaker": "1",
                    },
                    {
                        "start_time_sec": 2.5,
                        "end_time_sec": 3.5,
                        "text": "두 번째 발화",
                        "speaker": "2",
                    },
                ],
            )
        ]
    )

    assert [(segment.start_time_sec, segment.end_time_sec) for segment in segments] == [
        (10.5, 11.5),
        (20.25, 21.25),
    ]
    assert render_plain_text(segments) == "첫 번째 발화\n두 번째 발화"


def test_merge_removes_adjacent_exact_duplicate() -> None:
    mappings = [
        {
            "chunk_start_sec": 0.0,
            "chunk_end_sec": 2.0,
            "source_start_sec": 0.0,
            "source_end_sec": 2.0,
        }
    ]
    segments = merge_chunk_segments(
        [
            (
                mappings,
                [
                    {
                        "start_time_sec": 0.0,
                        "end_time_sec": 1.0,
                        "text": "같은 문장입니다.",
                        "confidence": 0.8,
                    },
                    {
                        "start_time_sec": 0.8,
                        "end_time_sec": 1.5,
                        "text": "같은 문장입니다",
                        "confidence": 0.9,
                    },
                ],
            )
        ]
    )

    assert len(segments) == 1
    assert segments[0].confidence == 0.9


def test_merge_maps_padding_gap_to_nearest_source_boundary() -> None:
    mappings = [
        {
            "chunk_start_sec": 0.0,
            "chunk_end_sec": 2.0,
            "source_start_sec": 10.0,
            "source_end_sec": 12.0,
        },
        {
            "chunk_start_sec": 2.4,
            "chunk_end_sec": 4.4,
            "source_start_sec": 20.0,
            "source_end_sec": 22.0,
        },
    ]

    assert map_chunk_time(2.1, mappings) == 12.0
    assert map_chunk_time(2.3, mappings) == 20.0
