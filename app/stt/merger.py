from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MergedSegment:
    start_time_sec: float
    end_time_sec: float
    text: str
    speaker: str | None = None
    confidence: float | None = None


def merge_chunk_segments(
    chunks: list[tuple[list[dict[str, float]], list[dict[str, Any]]]],
) -> list[MergedSegment]:
    merged: list[MergedSegment] = []
    for mappings, segments in chunks:
        for segment in segments:
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            start = map_chunk_time(float(segment.get("start_time_sec") or 0), mappings)
            end = map_chunk_time(float(segment.get("end_time_sec") or 0), mappings)
            if end < start:
                end = start
            candidate = MergedSegment(
                start_time_sec=start,
                end_time_sec=end,
                text=text,
                speaker=_optional_string(segment.get("speaker")),
                confidence=_optional_float(segment.get("confidence")),
            )
            if merged and _is_exact_duplicate(merged[-1], candidate):
                merged[-1] = _prefer_segment(merged[-1], candidate)
            else:
                merged.append(candidate)
    return sorted(merged, key=lambda item: (item.start_time_sec, item.end_time_sec))


def map_chunk_time(value: float, mappings: list[dict[str, float]]) -> float:
    if not mappings:
        return value
    for index, mapping in enumerate(mappings):
        chunk_start = float(mapping["chunk_start_sec"])
        chunk_end = float(mapping["chunk_end_sec"])
        if chunk_start <= value <= chunk_end:
            source_start = float(mapping["source_start_sec"])
            source_end = float(mapping["source_end_sec"])
            mapped = source_start + (value - chunk_start)
            return min(mapped, source_end)
        if index and value < chunk_start:
            previous = mappings[index - 1]
            previous_chunk_end = float(previous["chunk_end_sec"])
            if value - previous_chunk_end <= chunk_start - value:
                return float(previous["source_end_sec"])
            return float(mapping["source_start_sec"])
    first = mappings[0]
    if value < float(first["chunk_start_sec"]):
        return float(first["source_start_sec"])
    return float(mappings[-1]["source_end_sec"])


def render_plain_text(segments: list[MergedSegment]) -> str:
    return "\n".join(segment.text for segment in segments)


def _is_exact_duplicate(left: MergedSegment, right: MergedSegment) -> bool:
    return _normalize(left.text) == _normalize(right.text) and right.start_time_sec <= left.end_time_sec + 0.5


def _prefer_segment(left: MergedSegment, right: MergedSegment) -> MergedSegment:
    if right.confidence is not None and (left.confidence is None or right.confidence > left.confidence):
        return right
    return left if len(left.text) >= len(right.text) else right


def _normalize(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None and value != "" else None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
