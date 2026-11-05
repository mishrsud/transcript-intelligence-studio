from dataclasses import dataclass
from typing import Literal, Protocol


class TranscriptError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Segment:
    text: str
    start: float
    duration: float


@dataclass(frozen=True)
class Transcript:
    video_id: str
    language: str
    source: Literal['manual', 'automatic', 'speech_to_text']
    retrieved_at: str
    segments: tuple[Segment, ...]


class CaptionProvider(Protocol):
    def fetch(self, video_id: str, language: str) -> Transcript: ...
