from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .terms.term_dictionary import DomainTerm, TermDictionary


@dataclass(frozen=True)
class CorrectionLog:
    original: str
    corrected: str
    term_id: str
    policy: str
    confidence: float
    start: int
    end: int
    action: str = "replaced"


@dataclass(frozen=True)
class UnmatchedCandidate:
    text: str
    reason: str
    start: int | None = None
    end: int | None = None


class RuleBasedCorrector:
    def __init__(self, term_dictionary: TermDictionary | None = None, context_window: int = 40):
        self.term_dictionary = term_dictionary or TermDictionary()
        self.context_window = context_window
        self._patterns = self._build_patterns()

    def correct(self, text: str) -> dict:
        logs: list[CorrectionLog] = []
        unmatched: list[UnmatchedCandidate] = []
        matches = self._collect_matches(text)
        corrected_text = self._render_corrected_text(text, matches, logs, unmatched)

        protected_terms = self._protected_terms(logs)
        return {
            "corrected_text": corrected_text,
            "correction_logs": [asdict(log) for log in logs],
            "protected_terms": protected_terms,
            "unmatched_candidates": [asdict(candidate) for candidate in unmatched],
        }

    def _build_patterns(self) -> list[tuple[str, DomainTerm]]:
        phrase_terms: list[tuple[str, DomainTerm]] = []
        for term in self.term_dictionary.iter_matchable_terms():
            for phrase in term.match_phrases:
                phrase_terms.append((phrase, term))
        return sorted(phrase_terms, key=lambda item: len(item[0]), reverse=True)

    def _collect_matches(self, text: str) -> list[tuple[int, int, str, DomainTerm, str]]:
        candidates: list[tuple[int, int, str, DomainTerm, str]] = []
        seen: set[tuple[int, int, str]] = set()

        for phrase, term in self._patterns:
            pattern = self._compile_phrase_pattern(phrase)
            for match in pattern.finditer(text):
                action = self._decide_action(text, match.start(), match.end(), term)
                key = (match.start(), match.end(), term.term_id)
                if key in seen:
                    continue
                candidates.append((match.start(), match.end(), match.group(0), term, action))
                seen.add(key)

        candidates.sort(
            key=lambda item: (
                item[0],
                0 if item[4] == "replaced" else 1,
                -(item[1] - item[0]),
                item[3].term_id,
            )
        )
        selected: list[tuple[int, int, str, DomainTerm, str]] = []
        cursor = -1
        for candidate in candidates:
            start, end, _, _, _ = candidate
            if start < cursor:
                continue
            selected.append(candidate)
            cursor = end
        return selected

    def _render_corrected_text(
        self,
        text: str,
        matches: list[tuple[int, int, str, DomainTerm, str]],
        logs: list[CorrectionLog],
        unmatched: list[UnmatchedCandidate],
    ) -> str:
        segments: list[str] = []
        cursor = 0

        for start, end, original, term, action in matches:
            if cursor < start:
                segments.append(text[cursor:start])

            logs.append(self._log(original, term, start, end, action))
            if action == "replaced":
                segments.append(term.canonical)
            else:
                segments.append(original)
                unmatched.append(
                    UnmatchedCandidate(
                        text=original,
                        reason=f"{term.replace_policy}:{term.term_id}",
                        start=start,
                        end=end,
                    )
                )
            cursor = end

        if cursor < len(text):
            segments.append(text[cursor:])
        return "".join(segments)

    def _compile_phrase_pattern(self, phrase: str) -> re.Pattern[str]:
        escaped = re.escape(phrase)
        if re.search(r"[A-Za-z0-9]", phrase):
            return re.compile(rf"(?<![A-Za-z0-9_-]){escaped}(?![A-Za-z0-9_-])", re.IGNORECASE)
        return re.compile(escaped)

    def _decide_action(self, text: str, start: int, end: int, term: DomainTerm) -> str:
        if term.replace_policy == "safe":
            return "replaced"
        if term.replace_policy == "context_required":
            return "replaced" if self._has_context(text, start, end, term) else "candidate"
        return "candidate"

    def _has_context(self, text: str, start: int, end: int, term: DomainTerm) -> bool:
        if not term.context_keywords:
            return False
        left = max(0, start - self.context_window)
        right = min(len(text), end + self.context_window)
        context = (text[left:start] + " " + text[end:right]).lower()
        return any(keyword.lower() in context for keyword in term.context_keywords)

    def _log(self, original: str, term: DomainTerm, start: int, end: int, action: str) -> CorrectionLog:
        return CorrectionLog(
            original=original,
            corrected=term.canonical,
            term_id=term.term_id,
            policy=term.replace_policy,
            confidence=term.confidence,
            start=start,
            end=end,
            action=action,
        )

    def _protected_terms(self, logs: list[CorrectionLog]) -> list[str]:
        return sorted({log.corrected for log in logs if log.action == "replaced"})
