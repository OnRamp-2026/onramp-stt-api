from __future__ import annotations

import re
from dataclasses import dataclass

from .terms.term_dictionary import DomainTerm, TermDictionary


@dataclass(frozen=True)
class GlossaryEntry:
    term_id: str
    canonical: str
    variants: tuple[str, ...]


def build_glossary_entries(
    text: str,
    term_dictionary: TermDictionary,
    correction_logs: list[dict] | None = None,
    max_items: int = 30,
) -> list[GlossaryEntry]:
    normalized_text = _normalize_text(text)
    selected_ids: list[str] = []
    seen_ids: set[str] = set()
    terms_by_id = {term.term_id: term for term in term_dictionary.terms}

    for log in correction_logs or []:
        term_id = log.get("term_id")
        if term_id and term_id not in seen_ids and term_id in terms_by_id:
            selected_ids.append(term_id)
            seen_ids.add(term_id)

    for term in term_dictionary.terms:
        if term.term_id in seen_ids:
            continue
        phrases = (term.canonical, *term.aliases, *term.stt_variants)
        if any(_normalize_text(phrase) in normalized_text for phrase in phrases if phrase):
            selected_ids.append(term.term_id)
            seen_ids.add(term.term_id)
        if len(selected_ids) >= max_items:
            break

    entries: list[GlossaryEntry] = []
    for term_id in selected_ids[:max_items]:
        term = terms_by_id.get(term_id)
        if term is None:
            continue
        variants = []
        for phrase in [*term.aliases, *term.stt_variants]:
            normalized = phrase.strip()
            if normalized and normalized not in variants:
                variants.append(normalized)
        entries.append(GlossaryEntry(term_id=term.term_id, canonical=term.canonical, variants=tuple(variants[:8])))
    return entries


def render_glossary(entries: list[GlossaryEntry]) -> str:
    if not entries:
        return "- 없음"
    return "\n".join(
        f"- {entry.canonical} | variants: {', '.join(entry.variants) if entry.variants else '-'}"
        for entry in entries
    )


def term_by_id(term_dictionary: TermDictionary, term_id: str) -> DomainTerm | None:
    for term in term_dictionary.terms:
        if term.term_id == term_id:
            return term
    return None


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()
