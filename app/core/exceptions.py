class SttError(Exception):
    code = "stt_error"
    retryable = False


class StorageError(SttError):
    code = "storage_error"
    retryable = True


class InvalidAudioError(SttError):
    code = "invalid_audio"


class AudioLimitExceededError(InvalidAudioError):
    code = "audio_limit_exceeded"


class ProviderError(SttError):
    code = "provider_error"

    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
