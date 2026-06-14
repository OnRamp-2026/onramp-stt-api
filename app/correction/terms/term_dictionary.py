from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TERMS_PATH = Path(__file__).with_name("domain_terms.json")


@dataclass(frozen=True)
class DomainTerm:
    term_id: str
    canonical: str
    category: str
    aliases: tuple[str, ...]
    stt_variants: tuple[str, ...]
    description: str
    source: str
    confidence: float
    replace_policy: str
    source_url: str | None = None
    context_keywords: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict) -> DomainTerm:
        return cls(
            term_id=data["term_id"],
            canonical=data["canonical"],
            category=data["category"],
            aliases=tuple(data.get("aliases", [])),
            stt_variants=tuple(data.get("stt_variants", [])),
            description=data.get("description", ""),
            source=data.get("source", "manual"),
            confidence=float(data.get("confidence", 0.0)),
            replace_policy=data.get("replace_policy", "manual_review"),
            source_url=data.get("source_url"),
            context_keywords=tuple(data.get("context_keywords", [])),
        )

    @property
    def match_phrases(self) -> tuple[str, ...]:
        phrases = [*self.stt_variants, *self.aliases]
        seen: set[str] = set()
        unique: list[str] = []
        for phrase in phrases:
            normalized = phrase.strip()
            if normalized and normalized != self.canonical and normalized.lower() not in seen:
                unique.append(normalized)
                seen.add(normalized.lower())
        return tuple(unique)


class TermRepository(ABC):
    @abstractmethod
    def load_terms(self) -> list[DomainTerm]:
        """Load terms from the backing store."""

    @abstractmethod
    def load_version(self) -> str:
        """Load dictionary version metadata."""


class JsonTermRepository(TermRepository):
    def __init__(self, path: str | Path = DEFAULT_TERMS_PATH):
        self.path = Path(path)
        self._payload: dict | None = None

    def load_terms(self) -> list[DomainTerm]:
        payload = self._load_payload()
        return [DomainTerm.from_dict(item) for item in payload.get("terms", [])]

    def load_version(self) -> str:
        payload = self._load_payload()
        return str(payload.get("version", "unknown"))

    def _load_payload(self) -> dict:
        if self._payload is None:
            with self.path.open(encoding="utf-8") as file:
                self._payload = json.load(file)
        return self._payload


class RdbTermRepository(TermRepository):
    def load_terms(self) -> list[DomainTerm]:
        raise NotImplementedError("RDB term loading will be implemented when the schema is finalized.")

    def load_version(self) -> str:
        raise NotImplementedError("RDB term version loading will be implemented when the schema is finalized.")


class TermDictionary:
    def __init__(self, repository: TermRepository | None = None):
        self.repository = repository or JsonTermRepository()
        self.terms = self.repository.load_terms()
        self.version = self.repository.load_version()

    def iter_matchable_terms(self) -> Iterable[DomainTerm]:
        return (term for term in self.terms if term.match_phrases)

    def canonical_terms(self) -> list[str]:
        return sorted({term.canonical for term in self.terms})
