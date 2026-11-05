import asyncio
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from requests import HTTPError, Response
from youtube_transcript_api import YouTubeRequestFailed
from youtube_transcriber.models import TranscriptError
from youtube_transcriber.provider import YouTubeCaptionProvider
from youtube_transcriber.store import Store
from youtube_transcriber.limits import BodyLimit


def test_wrapped_http_failure_retries():
    response = Response()
    response.status_code = 503
    def fail(video):
        try:
            raise HTTPError('503 Service Unavailable', response=response)
        except HTTPError as exc:
            raise YouTubeRequestFailed(video, exc) from exc
    with pytest.raises(TranscriptError) as error:
        YouTubeCaptionProvider(SimpleNamespace(list=fail)).fetch('dQw4w9WgXcQ', 'en')
    assert error.value.code == 'temporary_failure'


def test_recovery_and_expiry(tmp_path):
    store = Store(tmp_path/'db')
    id = store.create('dQw4w9WgXcQ', 'en')
    assert store.claim()['id'] == id
    store.recover()
    assert store.get(id)['status'] == 'queued'
    store.finish(id, transcript={'segments': []})
    with patch('youtube_transcriber.store.time.time', return_value=store.get(id)['updated'] + 86401):
        assert store.create('dQw4w9WgXcQ', 'en') != id


def test_terminal_audio_cleanup(tmp_path):
    store = Store(tmp_path/'db')
    audio = tmp_path/'recording'
    audio.write_bytes(b'audio')
    id = store.create_audio(audio, 'en')
    store.finish(id, error={'code':'no_speech'})
    store.recover()
    assert not audio.exists()


@pytest.mark.parametrize('headers', [[], [(b'content-length', b'20')]])
def test_request_limit_before_parsing(headers):
    sent = []
    async def downstream(scope, receive, send):
        await receive()
    async def receive():
        return {'type':'http.request','body':b'x'*20,'more_body':False}
    async def send(message):
        sent.append(message)
    asyncio.run(BodyLimit(downstream, max_bytes=10)({'type':'http','method':'POST','path':'/uploads','headers':headers}, receive, send))
    assert sent[0]['status'] == 413
