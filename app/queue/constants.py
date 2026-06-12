STT_REQUEST_STREAM = "onramp:stt:requests:v1"
STT_CHUNK_STREAM = "onramp:stt:chunks:v1"
STT_PROGRESS_STREAM = "onramp:stt:progress:v1"
STT_TRANSCRIPT_COMPLETED_STREAM = "onramp:stt:transcript-completed:v1"
STT_COMMAND_STREAM = "onramp:stt:commands:v1"
STT_DLQ_STREAM = "onramp:stt:dlq:v1"

PROGRESS_EVENT_TYPE = "transcription.progress.updated"
TRANSCRIPT_COMPLETED_EVENT_TYPE = "transcription.transcript.completed"

ORCHESTRATOR_GROUP = "stt-orchestrators"
CLOVA_WORKER_GROUP = "clova-workers"
COMMAND_HANDLER_GROUP = "stt-command-handlers"

STREAM_GROUPS = {
    STT_REQUEST_STREAM: ORCHESTRATOR_GROUP,
    STT_CHUNK_STREAM: CLOVA_WORKER_GROUP,
    STT_COMMAND_STREAM: COMMAND_HANDLER_GROUP,
}
