from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict
from typing import Any

from app.core.config import Settings

from .glossary import build_glossary_entries, term_by_id
from .llm_client import LlmClient, OpenAiLlmClient
from .prompts import PROMPT_VERSION, build_correction_prompt
from .rule_based_corrector import RuleBasedCorrector
from .terms.term_dictionary import DomainTerm, JsonTermRepository, TermDictionary
from .types import CorrectedSegment, CorrectionAuditLog, CorrectionResult, ReviewCandidate
from .validators import choose_validated_output

logger = logging.getLogger(__name__)


class CorrectionService:
    def __init__(
        self,
        settings: Settings,
        *,
        llm_client: LlmClient | None = None,
        term_dictionary: TermDictionary | None = None,
    ) -> None:
        self.settings = settings
        self.term_dictionary = term_dictionary or TermDictionary(JsonTermRepository())
        self.rule_corrector = RuleBasedCorrector(self.term_dictionary)
        self.llm_client = llm_client

    def correct(self, raw_text: str, raw_segments: list[dict[str, Any]]) -> CorrectionResult:
        rule_result = self.rule_corrector.correct(raw_text)
        first_pass_text = rule_result["corrected_text"]
        glossary_entries = build_glossary_entries(
            raw_text,
            self.term_dictionary,
            rule_result["correction_logs"],
            max_items=self.settings.stt_correction_glossary_max_items,
        )
        final_text = first_pass_text
        llm_applied = False

        if self.settings.stt_correction_enable_llm:
            prompt = build_correction_prompt(
                raw_text=raw_text,
                first_pass_text=first_pass_text,
                glossary_entries=glossary_entries,
                review_candidates=rule_result["unmatched_candidates"],
            )
            client = self.llm_client
            if client is None and self.settings.openai_api_key:
                client = OpenAiLlmClient(self.settings)
            if client is not None:
                try:
                    candidate_text = client.complete(prompt)
                    final_text, llm_applied = choose_validated_output(
                        raw_text=raw_text,
                        fallback_text=first_pass_text,
                        candidate_text=candidate_text,
                        protected_terms=rule_result["protected_terms"],
                        min_ratio=self.settings.stt_correction_min_response_ratio,
                    )
                except Exception:
                    logger.warning("STT correction LLM failed; using rule-based result.", exc_info=True)

        corrected_segments = self._build_corrected_segments(raw_segments, final_text)
        correction_logs = self._build_correction_logs(
            raw_text=raw_text,
            corrected_text=final_text,
            raw_segments=raw_segments,
            logs=rule_result["correction_logs"],
            llm_applied=llm_applied,
        )
        review_candidates = self._build_review_candidates(
            raw_text=raw_text,
            raw_segments=raw_segments,
            candidates=rule_result["unmatched_candidates"],
        )

        return CorrectionResult(
            dictionary_version=self.term_dictionary.version,
            raw_text_sha256=_sha256(raw_text),
            corrected_text=final_text,
            corrected_segments=corrected_segments,
            corrected_text_sha256=_sha256(final_text),
            correction_logs=correction_logs,
            review_candidates=review_candidates,
            prompt_version=PROMPT_VERSION,
            llm_applied=llm_applied,
        )

    def _build_corrected_segments(
        self, raw_segments: list[dict[str, Any]], corrected_text: str
    ) -> list[CorrectedSegment]:
        corrected_lines = corrected_text.splitlines()
        if len(corrected_lines) != len(raw_segments):
            corrected_lines = [str(segment.get("text") or "") for segment in raw_segments]
        return [
            CorrectedSegment(
                start_time_sec=float(segment.get("start_time_sec") or 0.0),
                end_time_sec=float(segment.get("end_time_sec") or 0.0),
                text=corrected_lines[index],
                speaker=str(segment.get("speaker")) if segment.get("speaker") not in (None, "") else None,
                confidence=float(segment["confidence"]) if segment.get("confidence") is not None else None,
            )
            for index, segment in enumerate(raw_segments)
        ]

    def _build_correction_logs(
        self,
        *,
        raw_text: str,
        corrected_text: str,
        raw_segments: list[dict[str, Any]],
        logs: list[dict[str, Any]],
        llm_applied: bool,
    ) -> list[CorrectionAuditLog]:
        line_ranges = _line_ranges(raw_text)
        corrected_lines = corrected_text.splitlines()
        audit_logs: list[CorrectionAuditLog] = []
        for log in logs:
            segment_index = _segment_index_for_range(int(log["start"]), line_ranges)
            if segment_index is None or segment_index >= len(raw_segments):
                continue
            raw_segment = raw_segments[segment_index]
            original_text = str(raw_segment.get("text") or "")
            corrected_segment_text = (
                corrected_lines[segment_index] if segment_index < len(corrected_lines) else original_text
            )
            term = term_by_id(self.term_dictionary, str(log["term_id"]))
            context_evidence = _context_evidence(raw_segments, segment_index, term)
            if log["action"] == "candidate":
                if (
                    llm_applied
                    and corrected_segment_text != original_text
                    and term is not None
                    and term.canonical in corrected_segment_text
                ):
                    decision = "llm_verified"
                else:
                    decision = "review_required"
            elif corrected_segment_text != original_text:
                decision = "replaced"
            else:
                decision = "kept"
            audit_logs.append(
                CorrectionAuditLog(
                    segment_index=segment_index,
                    start_time_sec=float(raw_segment.get("start_time_sec") or 0.0),
                    end_time_sec=float(raw_segment.get("end_time_sec") or 0.0),
                    term_id=str(log["term_id"]),
                    replace_policy=str(log["policy"]),
                    original_text=original_text,
                    corrected_text=corrected_segment_text,
                    context_evidence=context_evidence,
                    decision=decision,
                )
            )
        return audit_logs

    def _build_review_candidates(
        self,
        *,
        raw_text: str,
        raw_segments: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> list[ReviewCandidate]:
        line_ranges = _line_ranges(raw_text)
        review: list[ReviewCandidate] = []
        for candidate in candidates:
            start = candidate.get("start")
            segment_index = _segment_index_for_range(int(start), line_ranges) if start is not None else None
            if segment_index is None or segment_index >= len(raw_segments):
                continue
            raw_segment = raw_segments[segment_index]
            _, term_id = str(candidate["reason"]).split(":", 1)
            term = term_by_id(self.term_dictionary, term_id)
            review.append(
                ReviewCandidate(
                    segment_index=segment_index,
                    text=str(candidate["text"]),
                    canonical=term.canonical if term is not None else term_id,
                    reason=str(candidate["reason"]),
                    context_evidence=str(raw_segment.get("text") or ""),
                )
            )
        return review


def serialize_corrected_segments(segments: list[CorrectedSegment]) -> list[dict[str, Any]]:
    return [asdict(segment) for segment in segments]


def serialize_correction_logs(logs: list[CorrectionAuditLog]) -> list[dict[str, Any]]:
    return [asdict(log) for log in logs]


def serialize_review_candidates(candidates: list[ReviewCandidate]) -> list[dict[str, Any]]:
    return [asdict(candidate) for candidate in candidates]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line_ranges(text: str) -> list[tuple[int, int]]:
    lines = text.splitlines(keepends=True)
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for line in lines:
        start = cursor
        cursor += len(line)
        ranges.append((start, cursor))
    return ranges


def _segment_index_for_range(position: int, ranges: list[tuple[int, int]]) -> int | None:
    for index, (start, end) in enumerate(ranges):
        if start <= position < end:
            return index
    if ranges and position == ranges[-1][1]:
        return len(ranges) - 1
    return None


def _context_evidence(
    raw_segments: list[dict[str, Any]],
    segment_index: int,
    term: DomainTerm | None,
) -> str | None:
    if term is None or not term.context_keywords:
        return None
    start = max(0, segment_index - 1)
    end = min(len(raw_segments), segment_index + 2)
    evidence = [
        str(raw_segments[index].get("text") or "").strip()
        for index in range(start, end)
        if str(raw_segments[index].get("text") or "").strip()
    ]
    if not evidence:
        return None
    return " | ".join(evidence)
