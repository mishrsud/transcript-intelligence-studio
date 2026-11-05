import json
from types import SimpleNamespace

import pytest
from requests.exceptions import Timeout
from youtube_transcript_api import TranscriptsDisabled, RequestBlocked, VideoUnavailable

from youtube_transcriber.urls import parse_url
from youtube_transcriber.models import TranscriptError, Segment, Transcript
from youtube_transcriber.provider import YouTubeCaptionProvider
from youtube_transcriber.exports import render
from youtube_transcriber.cli import main

ID = 'dQw4w9WgXcQ'

@pytest.mark.parametrize('url', [f'https://www.youtube.com/watch?v={ID}&t=10', f'https://youtu.be/{ID}?si=abc', f'https://m.youtube.com/shorts/{ID}', f' http://youtube.com/watch?v={ID} '])
def test_urls(url):
    assert parse_url(url) == ID

@pytest.mark.parametrize('url', ['https://evil.com/watch?v='+ID, 'https://youtube.com.evil.com/watch?v='+ID, 'https://user@youtube.com/watch?v='+ID, 'file://youtube.com/watch?v='+ID, 'https://youtube.com:444/watch?v='+ID, 'https://youtube.com/watch?v=short', f'https://youtube.com/watch?v={ID}&v={ID}', f'https://youtu.be/{ID}/extra', f'https://youtube.com/embed/{ID}', ID])
def test_invalid_urls(url):
    with pytest.raises(TranscriptError, match='valid YouTube'):
        parse_url(url)

class Track:
    def __init__(self, lang='en', generated=False):
        self.language_code = lang
        self.is_generated = generated
    def fetch(self):
        return [SimpleNamespace(text='Hello & welcome', start=0.125, duration=1.5)]

class API:
    def __init__(self, tracks=None, error=None):
        self.tracks = tracks
        self.error = error
    def list(self, video_id):
        if self.error:
            raise self.error
        return self.tracks

@pytest.mark.parametrize('tracks,source', [([Track(generated=True), Track()], 'manual'), ([Track(generated=True)], 'automatic')])
def test_selection_and_normalization(tracks, source):
    result = YouTubeCaptionProvider(API(tracks)).fetch(ID, 'en')
    assert result.source == source
    assert result.video_id == ID
    assert result.language == 'en'
    assert result.segments == (Segment('Hello & welcome', 0.125, 1.5),)
    assert result.retrieved_at.endswith('+00:00')

@pytest.mark.parametrize('tracks,code', [([Track('fr')], 'language_unavailable'), ([], 'captions_missing')])
def test_missing_tracks(tracks, code):
    with pytest.raises(TranscriptError) as error:
        YouTubeCaptionProvider(API(tracks)).fetch(ID, 'en')
    assert error.value.code == code

@pytest.mark.parametrize('exception,code', [(TranscriptsDisabled(ID), 'captions_missing'), (RequestBlocked(ID), 'access_restricted'), (VideoUnavailable(ID), 'video_unavailable'), (Timeout(), 'temporary_failure')])
def test_provider_errors(exception, code):
    with pytest.raises(TranscriptError) as error:
        YouTubeCaptionProvider(API(error=exception)).fetch(ID, 'en')
    assert error.value.code == code

@pytest.fixture
def transcript():
    return Transcript(ID, 'en', 'manual', '2026-11-05T00:00:00+00:00', (Segment('Hello', 59.9996, 1.25), Segment('world', 3600, 0.5)))

def test_exports(transcript):
    assert render(transcript, 'txt') == 'Hello\nworld\n'
    assert '00:01:00,000 --> 00:01:01,250' in render(transcript, 'srt')
    assert '01:00:00,000 --> 01:00:00,500' in render(transcript, 'srt')
    assert json.loads(render(transcript, 'json'))['segments'][0]['start'] == 59.9996

def test_cli_success(capsys, transcript):
    provider = SimpleNamespace(fetch=lambda video_id, language: transcript)
    assert main([f'https://youtu.be/{ID}'], provider=provider) == 0
    assert json.loads(capsys.readouterr().out)['video_id'] == ID

def test_cli_error(capsys):
    assert main(['https://example.com'], provider=API()) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert json.loads(captured.err)['error']['code'] == 'invalid_url'
