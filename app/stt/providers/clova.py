from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.stt.providers.base import ProviderResult, ProviderSegment


class ClovaSpeechProvider:
    provider = "clova"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.naver_clova_speech_invoke_url:
            raise ValueError("NAVER_CLOVA_SPEECH_INVOKE_URL is required.")
        if not settings.naver_clova_speech_secret_key:
            raise ValueError("NAVER_CLOVA_SPEECH_SECRET_KEY is required.")
        self.settings = settings
        self.client = client

    async def transcribe(self, audio_path: Path) -> ProviderResult:
        params = self._build_params()
        files = {
            "media": (audio_path.name, audio_path.read_bytes(), "audio/wav"),
            "params": (None, json.dumps(params, ensure_ascii=False), "application/json"),
        }
        headers = {"X-CLOVASPEECH-API-KEY": self.settings.naver_clova_speech_secret_key}
        url = f"{self.settings.naver_clova_speech_invoke_url.rstrip('/')}/recognizer/upload"
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.settings.clova_request_timeout_sec)
        try:
            response = await client.post(url, headers=headers, files=files)
        except httpx.TimeoutException as exc:
            raise ProviderError("CLOVA Speech request timed out.", retryable=True) from exc
        except httpx.TransportError as exc:
            raise ProviderError("CLOVA Speech transport failed.", retryable=True) from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code >= 400:
            retryable = response.status_code == 429 or response.status_code >= 500
            raise ProviderError(
                f"CLOVA Speech returned HTTP {response.status_code}.",
                retryable=retryable,
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("CLOVA Speech returned invalid JSON.", retryable=False) from exc
        if not isinstance(payload, dict):
            raise ProviderError("CLOVA Speech returned an invalid response object.", retryable=False)
        return self._normalize(payload)

    @staticmethod
    def _build_params() -> dict[str, Any]:
        return {
            "language": "ko-KR",
            "completion": "sync",
            "fullText": True,
            "wordAlignment": True,
            "noiseFiltering": True,
            "diarization": {"enable": True},
        }

    def _normalize(self, payload: dict[str, Any]) -> ProviderResult:
        segments: list[ProviderSegment] = []
        raw_segments = payload.get("segments")
        if isinstance(raw_segments, list):
            for item in raw_segments:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                speaker_data = item.get("speaker")
                speaker = None
                if isinstance(speaker_data, dict):
                    speaker = str(speaker_data.get("label") or speaker_data.get("name") or "") or None
                elif speaker_data is not None:
                    speaker = str(speaker_data)
                segments.append(
                    ProviderSegment(
                        start_time_sec=self._milliseconds_to_seconds(item.get("start")),
                        end_time_sec=self._milliseconds_to_seconds(item.get("end")),
                        text=text,
                        speaker=speaker,
                        confidence=self._optional_float(item.get("confidence")),
                    )
                )
        full_text = str(payload.get("text") or payload.get("fullText") or "").strip()
        if not full_text:
            full_text = "\n".join(segment.text for segment in segments)
        return ProviderResult(
            provider=self.provider,
            provider_job_id=self._optional_string(payload.get("id")),
            full_text=full_text,
            segments=tuple(segments),
            raw_response=payload,
        )

    @staticmethod
    def _milliseconds_to_seconds(value: Any) -> float:
        try:
            return float(value) / 1000
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return str(value) if value is not None else None
