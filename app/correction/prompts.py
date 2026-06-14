from __future__ import annotations

from .glossary import GlossaryEntry, render_glossary

PROMPT_VERSION = "strict_glossary_segment_preserving_v1"


def build_correction_prompt(
    *,
    raw_text: str,
    first_pass_text: str,
    glossary_entries: list[GlossaryEntry],
    review_candidates: list[dict],
) -> str:
    glossary = render_glossary(glossary_entries)
    review_text = ", ".join(
        f"{candidate.get('text')} ({candidate.get('reason')})"
        for candidate in review_candidates
        if candidate.get("text")
    )
    if not review_text:
        review_text = "없음"

    return f"""다음은 회의 STT 원문을 segment별로 한 줄씩 정리한 입력입니다.

규칙:
- 출력은 반드시 입력과 같은 줄 수, 같은 줄 순서를 유지하세요.
- 줄을 합치거나 나누지 마세요.
- 회의 내용을 요약하거나 새로 쓰지 마세요.
- 원문에 없는 사실, 결정, 조치, 원인을 추가하지 마세요.
- 기술 용어는 아래 glossary 기준 canonical 표기로 통일하세요.
- canonical이 영문/약어면 한국어 음역으로 남기지 말고 canonical 그대로 유지하세요.
- STT 오인식과 어색한 문맥만 최소한으로 교정하세요.
- 이미 1차로 보정된 표현이 더 자연스러우면 그 표현을 유지해도 됩니다.
- 검토 후보는 문맥이 확실할 때만 교정하고, 애매하면 원문이나 1차 교정값을 유지하세요.
- 최종 출력은 교정된 줄들만 그대로 출력하세요.

참고 glossary:
{glossary}

검토 후보:
{review_text}

원문:
{raw_text}

1차 교정안:
{first_pass_text}
"""
