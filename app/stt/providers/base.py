from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderSegment:
    start_time_sec: float
    end_time_sec: float
    text: str
    speaker: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    full_text: str
    segments: tuple[ProviderSegment, ...]
    raw_response: dict[str, Any] = field(default_factory=dict)
    provider_job_id: str | None = None


class STTProvider(Protocol):
    async def transcribe(self, audio_path: Path) -> ProviderResult: ...
