from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "OnRamp STT API"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5434/onramp_stt"
    redis_url: str = "redis://localhost:6380/0"

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: Path = Path("data")
    storage_bucket: str = "onramp-stt"
    storage_endpoint_url: str = ""
    storage_region: str = "ap-northeast-2"
    storage_access_key: str = ""
    storage_secret_key: str = ""

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    stt_max_upload_bytes: int = Field(default=2_147_483_648, ge=1)
    stt_max_audio_duration_sec: float = Field(default=14_400, gt=0)

    stt_vad_aggressiveness: int = Field(default=1, ge=0, le=3)
    stt_vad_frame_ms: Literal[10, 20, 30] = 30
    stt_vad_padding_ms: int = Field(default=500, ge=30)
    stt_vad_trigger_ratio: float = Field(default=0.8, gt=0, le=1)
    stt_vad_max_chunk_seconds: float = Field(default=55, gt=0)
    stt_vad_gap_ms: int = Field(default=250, ge=0)

    naver_clova_speech_invoke_url: str = ""
    naver_clova_speech_secret_key: str = ""
    clova_request_timeout_sec: float = Field(default=180, gt=0)
    clova_max_concurrent_jobs: int = Field(default=2, ge=1)
    clova_max_retry_count: int = Field(default=3, ge=0)
    clova_backoff_base_sec: float = Field(default=2, ge=0)
    clova_backoff_max_sec: float = Field(default=60, ge=0)
    clova_semaphore_lease_sec: int = Field(default=240, ge=1)
    clova_chunk_lease_sec: int = Field(default=600, ge=1)

    redis_stream_block_ms: int = Field(default=5000, ge=1)
    redis_stream_read_count: int = Field(default=10, ge=1)
    redis_pending_reclaim_idle_ms: int = Field(default=300000, ge=1)

    @field_validator("stt_vad_frame_ms", mode="before")
    @classmethod
    def _coerce_frame_ms(cls, value: object) -> object:
        if isinstance(value, str):
            return int(value)
        return value

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
