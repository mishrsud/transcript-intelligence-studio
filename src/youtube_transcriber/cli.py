import argparse
import json
import sys

from .exports import render
from .models import CaptionProvider, TranscriptError
from .provider import YouTubeCaptionProvider
from .urls import parse_url


def main(argv=None, *, provider: CaptionProvider | None = None) -> int:
    parser = argparse.ArgumentParser(description='Fetch YouTube captions, preferring manual tracks.')
    parser.add_argument('url')
    parser.add_argument('--language', default='en', help='Exact caption language code (default: en)')
    parser.add_argument('--format', choices=['json', 'txt', 'srt'], default='json')
    args = parser.parse_args(argv)
    try:
        video_id = parse_url(args.url)
        result = (provider if provider is not None else YouTubeCaptionProvider()).fetch(video_id, args.language)
        sys.stdout.write(render(result, args.format))
        return 0
    except TranscriptError as exc:
        print(json.dumps({'error': {'code': exc.code, 'message': str(exc)}}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
