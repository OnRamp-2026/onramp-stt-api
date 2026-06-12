import json
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.stt.providers.clova import ClovaSpeechProvider


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        naver_clova_speech_invoke_url="https://clova.test/domain",
        naver_clova_speech_secret_key="secret",
    )


async def test_clova_provider_uses_ko_kr_without_boosting(tmp_path: Path) -> None:
    captured_body = b""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        captured_body = request.content
        return httpx.Response(
            200,
            json={
                "text": "팟 상태를 확인합니다.",
                "segments": [
                    {
                        "start": 1000,
                        "end": 2500,
                        "text": "팟 상태를 확인합니다.",
                        "speaker": {"label": "1"},
                        "confidence": 0.91,
                    }
                ],
            },
        )

    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFF-test")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ClovaSpeechProvider(make_settings(), client).transcribe(audio)

    body_text = captured_body.decode(errors="ignore")
    assert '"language": "ko-KR"' in body_text
    assert '"completion": "sync"' in body_text
    assert "boostings" not in body_text
    assert "useDomainBoostings" not in body_text
    assert result.segments[0].start_time_sec == 1.0
    assert result.segments[0].speaker == "1"


async def test_clova_provider_marks_429_retryable(tmp_path: Path) -> None:
    audio = tmp_path / "chunk.wav"
    audio.write_bytes(b"RIFF-test")
    transport = httpx.MockTransport(lambda _: httpx.Response(429, text=json.dumps({"message": "busy"})))

    async with httpx.AsyncClient(transport=transport) as client:
        provider = ClovaSpeechProvider(make_settings(), client)
        with pytest.raises(ProviderError) as error:
            await provider.transcribe(audio)

    assert error.value.retryable is True
