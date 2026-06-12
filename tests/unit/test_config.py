from app.core.config import Settings


def test_settings_use_relaxed_vad_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.stt_vad_aggressiveness == 1
    assert settings.stt_vad_padding_ms == 500
    assert settings.stt_vad_trigger_ratio == 0.8
    assert settings.stt_vad_max_chunk_seconds == 55
