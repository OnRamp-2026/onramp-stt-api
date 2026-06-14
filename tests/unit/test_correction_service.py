from __future__ import annotations

from app.core.config import Settings
from app.correction.service import CorrectionService


class FakeLlmClient:
    def __init__(self, response: str):
        self.response = response

    def complete(self, prompt: str) -> str:
        return self.response


class FailingLlmClient:
    def complete(self, prompt: str) -> str:
        raise TimeoutError("temporary LLM timeout")


def test_correction_service_preserves_segment_shape_and_applies_llm_output() -> None:
    settings = Settings(
        stt_correction_enable_llm=True,
        openai_api_key="test-key",
    )
    raw_segments = [
        {"start_time_sec": 0.0, "end_time_sec": 1.0, "text": "컴퍼런스 문서를 열어주세요."},
        {"start_time_sec": 1.0, "end_time_sec": 2.0, "text": "그게 더 절연해요."},
    ]
    raw_text = "컴퍼런스 문서를 열어주세요.\n그게 더 절연해요."
    service = CorrectionService(
        settings,
        llm_client=FakeLlmClient("Confluence 문서를 열어주세요.\n그게 더 저렴해요."),
    )

    result = service.correct(raw_text, raw_segments)

    assert result.corrected_text == "Confluence 문서를 열어주세요.\n그게 더 저렴해요."
    assert len(result.corrected_segments) == 2
    assert result.corrected_segments[0].text == "Confluence 문서를 열어주세요."
    assert result.corrected_segments[1].text == "그게 더 저렴해요."
    assert result.correction_logs[0].decision == "replaced"
    assert result.llm_applied is True


def test_correction_service_falls_back_when_llm_changes_line_count() -> None:
    settings = Settings(
        stt_correction_enable_llm=True,
        openai_api_key="test-key",
    )
    raw_segments = [
        {"start_time_sec": 0.0, "end_time_sec": 1.0, "text": "컴퍼런스 문서를 열어주세요."},
        {"start_time_sec": 1.0, "end_time_sec": 2.0, "text": "슬랙으로 공유해주세요."},
    ]
    raw_text = "컴퍼런스 문서를 열어주세요.\n슬랙으로 공유해주세요."
    service = CorrectionService(
        settings,
        llm_client=FakeLlmClient("Confluence 문서를 열어주세요. Slack으로 공유해주세요."),
    )

    result = service.correct(raw_text, raw_segments)

    assert result.corrected_text == "Confluence 문서를 열어주세요.\nSlack으로 공유해주세요."
    assert result.llm_applied is False
    assert len(result.corrected_segments) == 2


def test_correction_service_marks_safe_dictionary_replacements() -> None:
    settings = Settings(
        stt_correction_enable_llm=False,
        openai_api_key="",
    )
    raw_segments = [
        {"start_time_sec": 0.0, "end_time_sec": 1.0, "text": "슬랙으로 공유해주세요."},
    ]
    raw_text = "슬랙으로 공유해주세요."
    service = CorrectionService(settings)

    result = service.correct(raw_text, raw_segments)

    assert result.corrected_text == "Slack으로 공유해주세요."
    assert len(result.correction_logs) == 1
    assert result.correction_logs[0].decision == "replaced"
    assert result.llm_applied is False


def test_correction_service_marks_llm_verified_for_candidate_resolution() -> None:
    settings = Settings(
        stt_correction_enable_llm=True,
        openai_api_key="test-key",
    )
    raw_segments = [
        {"start_time_sec": 0.0, "end_time_sec": 1.0, "text": "컴퍼런스 열어주세요."},
    ]
    raw_text = "컴퍼런스 열어주세요."
    service = CorrectionService(
        settings,
        llm_client=FakeLlmClient("Confluence 열어주세요."),
    )

    result = service.correct(raw_text, raw_segments)

    assert result.corrected_text == "Confluence 열어주세요."
    assert len(result.correction_logs) == 1
    assert result.correction_logs[0].decision == "llm_verified"
    assert result.llm_applied is True


def test_correction_service_falls_back_to_rules_when_llm_fails() -> None:
    settings = Settings(
        stt_correction_enable_llm=True,
        openai_api_key="test-key",
    )
    raw_segments = [
        {"start_time_sec": 0.0, "end_time_sec": 1.0, "text": "슬랙으로 공유해주세요."},
    ]
    service = CorrectionService(settings, llm_client=FailingLlmClient())

    result = service.correct("슬랙으로 공유해주세요.", raw_segments)

    assert result.corrected_text == "Slack으로 공유해주세요."
    assert result.llm_applied is False
