from __future__ import annotations


def choose_validated_output(
    *,
    raw_text: str,
    fallback_text: str,
    candidate_text: str,
    protected_terms: list[str],
    min_ratio: float,
) -> tuple[str, bool]:
    normalized = candidate_text.strip()
    if not normalized:
        return fallback_text, False

    raw_lines = raw_text.splitlines()
    candidate_lines = normalized.splitlines()
    if len(raw_lines) != len(candidate_lines):
        return fallback_text, False

    if raw_text.strip():
        ratio = len(normalized) / max(1, len(raw_text.strip()))
        if ratio < min_ratio:
            return fallback_text, False

    for term in protected_terms:
        if term not in normalized and term in fallback_text:
            return fallback_text, False

    return normalized, True
