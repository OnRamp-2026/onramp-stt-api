from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.exceptions import AudioLimitExceededError, InvalidAudioError


@dataclass(frozen=True)
class AudioMetadata:
    duration_sec: float
    size_bytes: int
    format_name: str
    codec_name: str
    sample_rate: int | None
    channels: int | None


class AudioConverter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def probe(self, source: Path) -> AudioMetadata:
        process = await asyncio.create_subprocess_exec(
            self.settings.ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name,size:stream=codec_type,codec_name,sample_rate,channels",
            "-of",
            "json",
            str(source),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode(errors="replace").strip()
            raise InvalidAudioError(f"ffprobe rejected the audio: {message}")

        try:
            payload: dict[str, Any] = json.loads(stdout)
            format_data = payload["format"]
            audio_stream = next(stream for stream in payload.get("streams", []) if stream.get("codec_type") == "audio")
            metadata = AudioMetadata(
                duration_sec=float(format_data["duration"]),
                size_bytes=int(format_data.get("size") or source.stat().st_size),
                format_name=str(format_data["format_name"]),
                codec_name=str(audio_stream["codec_name"]),
                sample_rate=int(audio_stream["sample_rate"]) if audio_stream.get("sample_rate") else None,
                channels=int(audio_stream["channels"]) if audio_stream.get("channels") else None,
            )
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InvalidAudioError("ffprobe returned incomplete audio metadata.") from exc

        self._validate_limits(metadata)
        return metadata

    async def convert_to_pcm_wav(self, source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            self.settings.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(destination),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode(errors="replace").strip()
            raise InvalidAudioError(f"ffmpeg failed to normalize the audio: {message}")
        return destination

    def _validate_limits(self, metadata: AudioMetadata) -> None:
        if metadata.size_bytes > self.settings.stt_max_upload_bytes:
            raise AudioLimitExceededError("Audio file exceeds the configured size limit.")
        if metadata.duration_sec > self.settings.stt_max_audio_duration_sec:
            raise AudioLimitExceededError("Audio duration exceeds the configured limit.")
