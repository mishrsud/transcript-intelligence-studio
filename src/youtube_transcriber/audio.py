"""Local, optional speech-to-text; media decoding is bounded before inference."""
from datetime import datetime, timezone
import os

from .models import Segment, Transcript, TranscriptError


def normalize_segments(segments):
    # Whisper returns absolute offsets across its internal 30-second windows.
    # Keep them intact: independently concatenating overlapping chunks duplicates words.
    return tuple(Segment(s.text.strip(), s.start, s.end - s.start) for s in segments if s.text.strip())


def decode_bounded(path, max_seconds=3600):
    import av
    import numpy as np
    samples = []
    count = 0
    try:
        with av.open(str(path)) as container:
            if not container.streams.audio:
                raise TranscriptError('invalid_audio', 'The file contains no audio track.')
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            def append(frame):
                nonlocal count
                array = frame.to_ndarray().flatten()
                count += len(array)
                if count > max_seconds * 16000:
                    raise TranscriptError('audio_too_long', 'Audio must be 60 minutes or shorter.')
                samples.append(array)
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame):
                    append(converted)
            for converted in resampler.resample(None):
                append(converted)
    except (av.error.FFmpegError, ValueError) as exc:
        raise TranscriptError('invalid_audio', 'This file could not be decoded as audio. Try WAV, MP3, M4A, or MP4.') from exc
    if not samples:
        raise TranscriptError('invalid_audio', 'The file has no decodable audio.')
    return np.concatenate(samples).astype(np.float32) / 32768.0


class LocalSpeechProvider:
    def __init__(self):
        self.model = None

    def fetch_file(self, path, language):
        try:
            audio = decode_bounded(path)
            if self.model is None:
                from faster_whisper import WhisperModel
                self.model = WhisperModel(os.getenv('TRANSCRIBER_MODEL', 'tiny'), device='cpu', compute_type='int8', download_root=os.getenv('TRANSCRIBER_MODEL_DIR', 'data/models'))
            raw, info = self.model.transcribe(audio, language=language.split('-')[0], beam_size=5, vad_filter=True, condition_on_previous_text=True)
            segments = normalize_segments(raw)
            if not segments:
                raise TranscriptError('no_speech', 'No speech was detected in this recording.')
            return Transcript('audio', info.language, 'speech_to_text', datetime.now(timezone.utc).isoformat(), segments)
        except ImportError as exc:
            raise TranscriptError('speech_unavailable', 'Install the audio extra to enable local transcription.') from exc
        except TranscriptError:
            raise
        except Exception as exc:
            raise TranscriptError('speech_failure', 'Local transcription failed. Check available memory and model download access, then retry.') from exc
