from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .term_dictionary import DEFAULT_TERMS_PATH

CATEGORY_PREFIXES = {
    "ai": "AI",
    "aws": "AWS",
    "aws_networking": "AWS_NET",
    "aws_security": "AWS_SEC",
    "aws_storage": "AWS_STORAGE",
    "cicd": "CICD",
    "deployment_strategy": "DEPLOY",
    "documentation": "DOC",
    "incident_status": "K8S_ERROR",
    "kubernetes": "K8S",
    "kubernetes_error": "K8S_ERROR",
    "kubernetes_security": "K8S_SEC",
    "kubernetes_storage": "K8S_STORAGE",
    "observability": "OBS",
}


def _normalize_phrase(value: str) -> str:
    return "".join(value.lower().split())


def _unique(items: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        unique.append(normalized)
        seen.add(key)
    return unique


def _term_phrases(term: dict) -> set[str]:
    phrases = {term.get("canonical", "")}
    phrases.update(term.get("aliases", []))
    phrases.update(term.get("stt_variants", []))
    return {_normalize_phrase(phrase) for phrase in phrases if phrase and phrase.strip()}


class JsonTermIngestionService:
    def __init__(self, terms_path: str | Path = DEFAULT_TERMS_PATH):
        self.terms_path = Path(terms_path)

    def upsert_term(
        self,
        *,
        canonical: str,
        category: str,
        aliases: list[str] | None = None,
        stt_variants: list[str] | None = None,
        description: str = "",
        source: str = "manual",
        confidence: float = 0.9,
        replace_policy: str = "manual_review",
        context_keywords: list[str] | None = None,
        source_url: str | None = None,
    ) -> dict:
        payload = self._load_terms_payload()
        terms = payload["terms"]
        normalized_inputs = {
            _normalize_phrase(value)
            for value in [canonical, *(aliases or []), *(stt_variants or [])]
            if value and value.strip()
        }
        existing = self._find_existing_term(terms, canonical, normalized_inputs)

        if existing is None:
            term_id = self._next_term_id(category, {term["term_id"] for term in terms})
            created = {
                "term_id": term_id,
                "canonical": canonical,
                "category": category,
                "aliases": _unique(list(aliases or [])),
                "stt_variants": _unique(list(stt_variants or [])),
                "description": description,
                "source": source,
                "confidence": float(confidence),
                "replace_policy": replace_policy,
            }
            if context_keywords:
                created["context_keywords"] = _unique(list(context_keywords))
            if source_url:
                created["source_url"] = source_url
            terms.append(created)
            self._write_terms_payload(payload)
            return {"action": "added", "term_id": term_id, "canonical": canonical}

        existing["aliases"] = _unique([*existing.get("aliases", []), *(aliases or [])])
        existing["stt_variants"] = _unique([*existing.get("stt_variants", []), *(stt_variants or [])])
        if context_keywords:
            existing["context_keywords"] = _unique([*existing.get("context_keywords", []), *context_keywords])
        if description and not existing.get("description"):
            existing["description"] = description
        if source_url and not existing.get("source_url"):
            existing["source_url"] = source_url
        existing["confidence"] = max(float(existing.get("confidence", 0.0)), float(confidence))
        if existing.get("replace_policy") == "manual_review" and replace_policy != "manual_review":
            existing["replace_policy"] = replace_policy
        self._write_terms_payload(payload)
        return {"action": "updated", "term_id": existing["term_id"], "canonical": existing["canonical"]}

    def promote_candidate(
        self,
        *,
        candidate: str,
        suggested_canonical: str,
        category: str,
        aliases: list[str] | None = None,
        stt_variants: list[str] | None = None,
        description: str = "",
        source: str = "approved_candidate",
        confidence: float = 0.88,
        replace_policy: str = "manual_review",
        context_keywords: list[str] | None = None,
        source_url: str | None = None,
    ) -> dict:
        return self.upsert_term(
            canonical=suggested_canonical,
            category=category,
            aliases=aliases or [],
            stt_variants=_unique([candidate, *(stt_variants or [])]),
            description=description,
            source=source,
            confidence=confidence,
            replace_policy=replace_policy,
            context_keywords=context_keywords or [],
            source_url=source_url,
        )

    def _load_terms_payload(self) -> dict:
        if self.terms_path.exists():
            payload = json.loads(self.terms_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Term dictionary payload must be a JSON object")
            return payload
        return {
            "version": date.today().isoformat(),
            "description": (
                "OnRamp STT correction term dictionary. "
                "The JSON schema mirrors the runtime term model for local operation."
            ),
            "terms": [],
        }

    def _write_terms_payload(self, payload: dict) -> None:
        payload["version"] = date.today().isoformat()
        self.terms_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _find_existing_term(self, terms: list[dict], canonical: str, normalized_inputs: set[str]) -> dict | None:
        canonical_key = canonical.lower()
        for term in terms:
            if term.get("canonical", "").lower() == canonical_key:
                return term
        for term in terms:
            if normalized_inputs & _term_phrases(term):
                return term
        return None

    def _next_term_id(self, category: str, existing_ids: set[str]) -> str:
        prefix = CATEGORY_PREFIXES.get(category, "EXT")
        max_value = 0
        for term_id in existing_ids:
            if not term_id.startswith(prefix + "_"):
                continue
            tail = term_id[len(prefix) + 1 :]
            if tail.isdigit():
                max_value = max(max_value, int(tail))
        return f"{prefix}_{max_value + 1:03d}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upsert or promote STT correction domain terms.")
    parser.add_argument("--terms-path", default=str(DEFAULT_TERMS_PATH), help="Path to domain_terms.json.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    upsert = subparsers.add_parser("upsert", help="Insert or update one canonical term.")
    upsert.add_argument("--canonical", required=True)
    upsert.add_argument("--category", required=True)
    upsert.add_argument("--alias", action="append", default=[])
    upsert.add_argument("--variant", action="append", default=[])
    upsert.add_argument("--description", default="")
    upsert.add_argument("--source", default="manual")
    upsert.add_argument("--confidence", type=float, default=0.9)
    upsert.add_argument("--replace-policy", default="manual_review")
    upsert.add_argument("--context-keyword", action="append", default=[])
    upsert.add_argument("--source-url", default=None)

    promote = subparsers.add_parser("promote-candidate", help="Promote one discovered candidate into domain_terms.")
    promote.add_argument("--candidate", required=True)
    promote.add_argument("--canonical", required=True)
    promote.add_argument("--category", required=True)
    promote.add_argument("--alias", action="append", default=[])
    promote.add_argument("--variant", action="append", default=[])
    promote.add_argument("--description", default="")
    promote.add_argument("--source", default="approved_candidate")
    promote.add_argument("--confidence", type=float, default=0.88)
    promote.add_argument("--replace-policy", default="manual_review")
    promote.add_argument("--context-keyword", action="append", default=[])
    promote.add_argument("--source-url", default=None)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    service = JsonTermIngestionService(args.terms_path)

    if args.command == "upsert":
        result = service.upsert_term(
            canonical=args.canonical,
            category=args.category,
            aliases=args.alias,
            stt_variants=args.variant,
            description=args.description,
            source=args.source,
            confidence=args.confidence,
            replace_policy=args.replace_policy,
            context_keywords=args.context_keyword,
            source_url=args.source_url,
        )
    else:
        result = service.promote_candidate(
            candidate=args.candidate,
            suggested_canonical=args.canonical,
            category=args.category,
            aliases=args.alias,
            stt_variants=args.variant,
            description=args.description,
            source=args.source,
            confidence=args.confidence,
            replace_policy=args.replace_policy,
            context_keywords=args.context_keyword,
            source_url=args.source_url,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
