from __future__ import annotations

import collections
import contextlib
import wave
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import webrtcvad

from app.core.config import Settings
from app.core.exceptions import InvalidAudioError

SUPPORTED_SAMPLE_RATES = {8000, 16000, 32000, 48000}


@dataclass(frozen=True)
class WavFormat:
    channels: int
    sample_width: int
    sample_rate: int


@dataclass(frozen=True)
class AudioFrame:
    data: bytes
    source_start_sec: float
    duration_sec: float

    @property
    def source_end_sec(self) -> float:
        return self.source_start_sec + self.duration_sec


@dataclass(frozen=True)
class SpeechSegment:
    frames: tuple[AudioFrame, ...]

    @property
    def source_start_sec(self) -> float:
        return self.frames[0].source_start_sec

    @property
    def source_end_sec(self) -> float:
        return self.frames[-1].source_end_sec

    @property
    def duration_sec(self) -> float:
        return sum(frame.duration_sec for frame in self.frames)


@dataclass(frozen=True)
class SourceMapping:
    chunk_start_sec: float
    chunk_end_sec: float
    source_start_sec: float
    source_end_sec: float


@dataclass(frozen=True)
class VadChunk:
    index: int
    path: Path
    duration_sec: float
    source_mappings: tuple[SourceMapping, ...]


def inspect_wav(path: Path) -> WavFormat:
    with contextlib.closing(wave.open(str(path), "rb")) as wav_file:
        wav_format = WavFormat(
            channels=wav_file.getnchannels(),
            sample_width=wav_file.getsampwidth(),
            sample_rate=wav_file.getframerate(),
        )
    validate_wav_format(wav_format)
    return wav_format


def validate_wav_format(wav_format: WavFormat) -> None:
    if wav_format.channels != 1:
        raise InvalidAudioError("VAD input must be mono.")
    if wav_format.sample_width != 2:
        raise InvalidAudioError("VAD input must use 16-bit PCM samples.")
    if wav_format.sample_rate not in SUPPORTED_SAMPLE_RATES:
        raise InvalidAudioError(f"Unsupported VAD sample rate: {wav_format.sample_rate}")


def iter_pcm_frames(path: Path, *, frame_duration_ms: int) -> Iterator[AudioFrame]:
    with contextlib.closing(wave.open(str(path), "rb")) as wav_file:
        wav_format = WavFormat(
            channels=wav_file.getnchannels(),
            sample_width=wav_file.getsampwidth(),
            sample_rate=wav_file.getframerate(),
        )
        validate_wav_format(wav_format)
        samples_per_frame = wav_format.sample_rate * frame_duration_ms // 1000
        frame_duration_sec = samples_per_frame / wav_format.sample_rate
        frame_index = 0
        while data := wav_file.readframes(samples_per_frame):
            expected_bytes = samples_per_frame * wav_format.sample_width
            if len(data) != expected_bytes:
                break
            yield AudioFrame(
                data=data,
                source_start_sec=frame_index * frame_duration_sec,
                duration_sec=frame_duration_sec,
            )
            frame_index += 1


def iter_speech_segments(
    frames: Iterator[AudioFrame],
    *,
    sample_rate: int,
    aggressiveness: int,
    frame_duration_ms: int,
    padding_ms: int,
    trigger_ratio: float,
) -> Iterator[SpeechSegment]:
    vad = webrtcvad.Vad(aggressiveness)
    frames_per_padding = max(1, padding_ms // frame_duration_ms)
    ring_buffer: collections.deque[tuple[AudioFrame, bool]] = collections.deque(maxlen=frames_per_padding)
    voiced_frames: list[AudioFrame] = []
    triggered = False

    for frame in frames:
        is_speech = vad.is_speech(frame.data, sample_rate)
        if not triggered:
            ring_buffer.append((frame, is_speech))
            voiced_count = sum(1 for _, voiced in ring_buffer if voiced)
            if len(ring_buffer) == ring_buffer.maxlen and voiced_count >= trigger_ratio * len(ring_buffer):
                triggered = True
                voiced_frames.extend(buffered_frame for buffered_frame, _ in ring_buffer)
                ring_buffer.clear()
            continue

        voiced_frames.append(frame)
        ring_buffer.append((frame, is_speech))
        unvoiced_count = sum(1 for _, voiced in ring_buffer if not voiced)
        if len(ring_buffer) == ring_buffer.maxlen and unvoiced_count >= trigger_ratio * len(ring_buffer):
            yield SpeechSegment(frames=tuple(voiced_frames))
            voiced_frames = []
            ring_buffer.clear()
            triggered = False

    if voiced_frames:
        yield SpeechSegment(frames=tuple(voiced_frames))


def split_segment(segment: SpeechSegment, *, max_chunk_seconds: float) -> Iterator[SpeechSegment]:
    current: list[AudioFrame] = []
    current_duration = 0.0
    for frame in segment.frames:
        if current and current_duration + frame.duration_sec > max_chunk_seconds:
            yield SpeechSegment(frames=tuple(current))
            current = []
            current_duration = 0.0
        current.append(frame)
        current_duration += frame.duration_sec
    if current:
        yield SpeechSegment(frames=tuple(current))


def iter_packed_segments(
    segments: Iterator[SpeechSegment],
    *,
    max_chunk_seconds: float,
    gap_ms: int,
) -> Iterator[tuple[SpeechSegment, ...]]:
    current: list[SpeechSegment] = []
    current_duration = 0.0
    gap_sec = gap_ms / 1000

    for original_segment in segments:
        for segment in split_segment(original_segment, max_chunk_seconds=max_chunk_seconds):
            added_duration = segment.duration_sec + (gap_sec if current else 0)
            if current and current_duration + added_duration > max_chunk_seconds:
                yield tuple(current)
                current = []
                current_duration = 0.0
                added_duration = segment.duration_sec
            current.append(segment)
            current_duration += added_duration
    if current:
        yield tuple(current)


def write_vad_chunk(
    path: Path,
    segments: tuple[SpeechSegment, ...],
    wav_format: WavFormat,
    *,
    gap_ms: int,
) -> tuple[float, tuple[SourceMapping, ...]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    gap_frames = int(wav_format.sample_rate * gap_ms / 1000)
    gap_bytes = b"\x00" * gap_frames * wav_format.sample_width
    chunk_cursor = 0.0
    mappings: list[SourceMapping] = []

    with wave.open(str(path), "wb") as output:
        output.setnchannels(wav_format.channels)
        output.setsampwidth(wav_format.sample_width)
        output.setframerate(wav_format.sample_rate)
        for index, segment in enumerate(segments):
            if index:
                output.writeframes(gap_bytes)
                chunk_cursor += gap_ms / 1000
            segment_start = chunk_cursor
            for frame in segment.frames:
                output.writeframes(frame.data)
            chunk_cursor += segment.duration_sec
            mappings.append(
                SourceMapping(
                    chunk_start_sec=segment_start,
                    chunk_end_sec=chunk_cursor,
                    source_start_sec=segment.source_start_sec,
                    source_end_sec=segment.source_end_sec,
                )
            )
    return chunk_cursor, tuple(mappings)


class VadChunker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def split(self, source: Path, output_dir: Path) -> list[VadChunk]:
        wav_format = inspect_wav(source)
        frames = iter_pcm_frames(source, frame_duration_ms=self.settings.stt_vad_frame_ms)
        segments = iter_speech_segments(
            frames,
            sample_rate=wav_format.sample_rate,
            aggressiveness=self.settings.stt_vad_aggressiveness,
            frame_duration_ms=self.settings.stt_vad_frame_ms,
            padding_ms=self.settings.stt_vad_padding_ms,
            trigger_ratio=self.settings.stt_vad_trigger_ratio,
        )
        packed = iter_packed_segments(
            segments,
            max_chunk_seconds=self.settings.stt_vad_max_chunk_seconds,
            gap_ms=self.settings.stt_vad_gap_ms,
        )

        chunks: list[VadChunk] = []
        for index, chunk_segments in enumerate(packed):
            path = output_dir / f"chunk_{index:04d}.wav"
            duration, mappings = write_vad_chunk(
                path,
                chunk_segments,
                wav_format,
                gap_ms=self.settings.stt_vad_gap_ms,
            )
            chunks.append(
                VadChunk(
                    index=index,
                    path=path,
                    duration_sec=duration,
                    source_mappings=mappings,
                )
            )
        if not chunks:
            raise InvalidAudioError("No speech segments were detected.")
        return chunks
