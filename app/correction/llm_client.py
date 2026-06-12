from __future__ import annotations

from typing import Protocol

from app.core.config import Settings


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str:
        """Return corrected text only."""


class OpenAiLlmClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def complete(self, prompt: str) -> str:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for STT correction.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the openai package to use OpenAI STT correction.") from exc

        client = OpenAI(api_key=self.settings.openai_api_key)
        response = client.responses.create(
            model=self.settings.stt_correction_model,
            input=prompt,
            temperature=0.0,
        )
        return response.output_text.strip()
