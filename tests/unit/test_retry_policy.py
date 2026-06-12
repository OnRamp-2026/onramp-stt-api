from app.core.config import Settings
from app.core.exceptions import ProviderError


def test_clova_retry_defaults_are_bounded() -> None:
    settings = Settings(_env_file=None)

    assert settings.clova_max_retry_count == 3
    assert settings.clova_backoff_base_sec == 2
    assert settings.clova_backoff_max_sec == 60
    assert settings.clova_max_concurrent_jobs == 2


def test_provider_error_preserves_retryability() -> None:
    error = ProviderError("temporary storage failure", retryable=True)

    assert error.retryable is True
