import re
from urllib.parse import parse_qs, urlsplit

from .models import TranscriptError


def parse_url(url: str) -> str:
    """Extract an ID without making requests to user-supplied hosts."""
    try:
        parts = urlsplit(url.strip())
        if parts.scheme not in {'http', 'https'} or parts.username or parts.password:
            raise ValueError
        if parts.port not in {None, 80 if parts.scheme == 'http' else 443}:
            raise ValueError
        if parts.hostname == 'youtu.be':
            video_id = parts.path.removeprefix('/')
        elif parts.hostname in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
            if parts.path == '/watch':
                ids = parse_qs(parts.query, keep_blank_values=True).get('v', [])
                if len(ids) != 1:
                    raise ValueError
                video_id = ids[0]
            elif parts.path.startswith('/shorts/'):
                video_id = parts.path.removeprefix('/shorts/')
            else:
                raise ValueError
        else:
            raise ValueError
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            raise ValueError
        return video_id
    except ValueError as exc:
        raise TranscriptError('invalid_url', 'Enter a valid YouTube watch, youtu.be, or Shorts URL.') from exc
