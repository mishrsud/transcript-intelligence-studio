from dataclasses import asdict
import json

from .models import Transcript


def timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f'{hours:02d}:{minute:02d}:{sec:02d},{ms:03d}'


def render(transcript: Transcript, format: str) -> str:
    if format == 'json':
        return json.dumps(asdict(transcript), ensure_ascii=False, indent=2) + '\n'
    if format == 'txt':
        return '\n'.join(s.text for s in transcript.segments) + '\n'
    if format == 'srt':
        return '\n'.join(f'{i}\n{timestamp(s.start)} --> {timestamp(s.start + s.duration)}\n{s.text}\n' for i, s in enumerate(transcript.segments, 1))
    raise ValueError(f'Unsupported format: {format}')
