from __future__ import annotations

import json

from app.correction.terms.term_ingestion import JsonTermIngestionService


def test_term_ingestion_adds_new_term(tmp_path) -> None:
    terms_path = tmp_path / "domain_terms.json"
    terms_path.write_text(
        json.dumps(
            {
                "version": "2026-06-11",
                "description": "test",
                "terms": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = JsonTermIngestionService(terms_path)

    result = service.upsert_term(
        canonical="Confluence",
        category="documentation",
        aliases=["컨플루언스"],
        stt_variants=["컴퍼런스"],
        replace_policy="manual_review",
    )

    payload = json.loads(terms_path.read_text(encoding="utf-8"))

    assert result["action"] == "added"
    assert payload["terms"][0]["canonical"] == "Confluence"
    assert payload["terms"][0]["aliases"] == ["컨플루언스"]


def test_term_ingestion_updates_existing_term_by_alias_overlap(tmp_path) -> None:
    terms_path = tmp_path / "domain_terms.json"
    terms_path.write_text(
        json.dumps(
            {
                "version": "2026-06-11",
                "description": "test",
                "terms": [
                    {
                        "term_id": "DOC_001",
                        "canonical": "Confluence",
                        "category": "documentation",
                        "aliases": ["컨플루언스"],
                        "stt_variants": ["컴퍼런스"],
                        "description": "",
                        "source": "manual",
                        "confidence": 0.8,
                        "replace_policy": "manual_review",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = JsonTermIngestionService(terms_path)

    result = service.upsert_term(
        canonical="Confluence",
        category="documentation",
        aliases=["컨퍼런스"],
        stt_variants=["컨퍼런쓰"],
        replace_policy="safe",
    )

    payload = json.loads(terms_path.read_text(encoding="utf-8"))
    stored = payload["terms"][0]

    assert result["action"] == "updated"
    assert "컨퍼런스" in stored["aliases"]
    assert "컨퍼런쓰" in stored["stt_variants"]
    assert stored["replace_policy"] == "safe"
