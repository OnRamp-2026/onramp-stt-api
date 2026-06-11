import pytest

from app.core.config import Settings
from app.core.exceptions import AudioLimitExceededError
from app.stt.audio_converter import AudioConverter, AudioMetadata


def test_audio_converter_rejects_long_audio() -> None:
    settings = Settings(_env_file=None, stt_max_audio_duration_sec=60)
    converter = AudioConverter(settings)
    metadata = AudioMetadata(
        duration_sec=61,
        size_bytes=100,
        format_name="wav",
        codec_name="pcm_s16le",
        sample_rate=16000,
        channels=1,
    )

    with pytest.raises(AudioLimitExceededError):
        converter._validate_limits(metadata)
