from datetime import datetime, timezone
import math
import re

from requests import Session
from requests.exceptions import RequestException
from youtube_transcript_api import (
    YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound,
    RequestBlocked, AgeRestricted, PoTokenRequired, VideoUnavailable,
    VideoUnplayable, CouldNotRetrieveTranscript, YouTubeRequestFailed,
)

from .models import Segment, Transcript, TranscriptError


class TimeoutSession(Session):
    def request(self, method, url, **kwargs):
        kwargs.setdefault('timeout', (5, 20))
        return super().request(method, url, **kwargs)


class YouTubeCaptionProvider:
    def __init__(self, api=None):
        self.api = api if api is not None else YouTubeTranscriptApi(http_client=TimeoutSession())

    def fetch(self, video_id: str, language: str) -> Transcript:
        if not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', language):
            raise TranscriptError('invalid_language', 'Use a language code such as en or pt-BR.')
        try:
            tracks = list(self.api.list(video_id))
            if not tracks:
                raise TranscriptError('captions_missing', 'This video has no available captions.')
            matches = [t for t in tracks if t.language_code.lower() == language.lower()]
            if not matches:
                available = ', '.join(sorted({t.language_code for t in tracks}))
                raise TranscriptError('language_unavailable', f'No captions for {language}. Available: {available}.')
            track = min(matches, key=lambda t: t.is_generated)
            segments = tuple(Segment(s.text, s.start, s.duration) for s in track.fetch())
            if not segments:
                raise TranscriptError('captions_missing', 'The selected caption track is empty.')
            if any(not math.isfinite(s.start) or not math.isfinite(s.duration) or s.start < 0 or s.duration < 0 for s in segments):
                raise TranscriptError('provider_failure', 'The provider returned invalid caption timing.')
            return Transcript(video_id, track.language_code, 'automatic' if track.is_generated else 'manual', datetime.now(timezone.utc).isoformat(), segments)
        except TranscriptsDisabled as exc:
            raise TranscriptError('captions_missing', 'Captions are disabled or unavailable for this video.') from exc
        except NoTranscriptFound as exc:
            raise TranscriptError('language_unavailable', 'The requested caption language is unavailable.') from exc
        except (RequestBlocked, AgeRestricted, PoTokenRequired) as exc:
            raise TranscriptError('access_restricted', 'YouTube restricted caption access from this host or requires authentication.') from exc
        except (VideoUnavailable, VideoUnplayable) as exc:
            raise TranscriptError('video_unavailable', 'This video is unavailable or cannot be played from this host.') from exc
        except RequestException as exc:
            raise TranscriptError('temporary_failure', 'The caption request failed or timed out. Try again later.') from exc
        except YouTubeRequestFailed as exc:
            cause = exc.__cause__ or exc.__context__
            response = getattr(cause, 'response', None)
            status = getattr(response, 'status_code', None)
            if status in {408, 429, 500, 502, 503, 504}:
                raise TranscriptError('temporary_failure', 'YouTube is temporarily unavailable. Try again later.') from exc
            raise TranscriptError('provider_failure', 'YouTube rejected the caption request.') from exc
        except CouldNotRetrieveTranscript as exc:
            raise TranscriptError('provider_failure', 'YouTube caption retrieval failed. Its interface may have changed.') from exc
