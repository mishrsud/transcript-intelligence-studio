import time
from types import SimpleNamespace
from fastapi.testclient import TestClient
from youtube_transcriber.api import create_app
from youtube_transcriber.models import Transcript, Segment, TranscriptError


def wait(client, job):
    for _ in range(200):
        result = client.get('/transcripts/' + job).json()
        if result['status'] in {'completed', 'failed'}:
            return result
        time.sleep(.01)
    raise AssertionError('job did not finish')


def test_api_roundtrip_and_cache(tmp_path):
    calls = []
    def fetch(video, lang):
        calls.append(video)
        return Transcript(video, lang, 'manual', '2026-11-05T00:00:00+00:00', (Segment('Hello world', 0, 2),))
    app = create_app(tmp_path / 'jobs.db', SimpleNamespace(fetch=fetch))
    with TestClient(app) as client:
        assert client.post('/transcripts', json={'url': 'https://evil.com', 'language': 'en'}).status_code == 422
        payload = {'url': 'https://youtu.be/dQw4w9WgXcQ', 'language': 'en'}
        r = client.post('/transcripts', json=payload)
        assert r.status_code == 202
        job = r.json()['id']
        result = wait(client, job)
        assert result['status'] == 'completed'
        assert result['transcript']['segments'][0]['text'] == 'Hello world'
        assert client.get(f'/transcripts/{job}/export?format=txt').text == 'Hello world\n'
        assert '00:00:02,000' in client.get(f'/transcripts/{job}/export?format=srt').text
        assert client.get(f'/transcripts/{job}/export?format=bad').status_code == 422
        assert client.post('/transcripts', json=payload).json()['id'] == job
        assert len(calls) == 1
        assert client.get('/transcripts/unknown').status_code == 404


def test_failure_and_retry(tmp_path):
    calls = []
    def fetch(video, lang):
        calls.append(video)
        raise TranscriptError('temporary_failure', 'Try later')
    with TestClient(create_app(tmp_path / 'jobs.db', SimpleNamespace(fetch=fetch), retry_delay=0)) as client:
        job = client.post('/transcripts', json={'url': 'https://youtu.be/dQw4w9WgXcQ'}).json()['id']
        result = wait(client, job)
        assert result['status'] == 'failed'
        assert result['error']['code'] == 'temporary_failure'
        assert len(calls) == 3
        assert client.get(f'/transcripts/{job}/export').status_code == 409


def test_recorded_provider_response(tmp_path):
    import json
    from pathlib import Path
    from youtube_transcriber.provider import YouTubeCaptionProvider
    recorded = json.loads((Path(__file__).parent/'fixtures/manual_caption.json').read_text())
    track = SimpleNamespace(language_code=recorded['language_code'], is_generated=recorded['is_generated'], fetch=lambda: [SimpleNamespace(**s) for s in recorded['segments']])
    provider = YouTubeCaptionProvider(SimpleNamespace(list=lambda _: [track]))
    with TestClient(create_app(tmp_path/'db', provider)) as client:
        id = client.post('/transcripts', json={'url': 'https://youtu.be/'+recorded['video_id']}).json()['id']
        job = wait(client, id)
        assert job['transcript']['segments'] == recorded['segments']
