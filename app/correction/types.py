from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewCandidate:
    segment_index: int
    text: str
    canonical: str
    reason: str
    context_evidence: str


@dataclass(frozen=True)
class CorrectionAuditLog:
    segment_index: int
    start_time_sec: float
    end_time_sec: float
    term_id: str
    replace_policy: str
    original_text: str
    corrected_text: str
    context_evidence: str | None
    decision: str


@dataclass(frozen=True)
class CorrectedSegment:
    start_time_sec: float
    end_time_sec: float
    text: str
    speaker: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class CorrectionResult:
    dictionary_version: str
    raw_text_sha256: str
    corrected_text: str
    corrected_segments: list[CorrectedSegment]
    corrected_text_sha256: str
    correction_logs: list[CorrectionAuditLog]
    review_candidates: list[ReviewCandidate]
    prompt_version: str
    llm_applied: bool
