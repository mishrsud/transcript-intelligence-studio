from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from youtube_transcriber.api import create_app
from youtube_transcriber.models import Transcript, Segment
from youtube_transcriber.audio import LocalSpeechProvider, normalize_segments
from test_api import wait


def test_chunk_boundaries_preserve_text_and_offsets():
    chunks = [SimpleNamespace(text='Before the boundary', start=29.1, end=30.0), SimpleNamespace(text='after the boundary.', start=30.0, end=31.4)]
    result = normalize_segments(iter(chunks))
    assert [s.text for s in result] == ['Before the boundary', 'after the boundary.']
    assert result[0].start + result[0].duration == result[1].start
    assert result[1].start == 30


def test_upload_job_deletes_file(tmp_path):
    seen = []
    def fetch_file(path, language):
        seen.append(Path(path))
        assert Path(path).read_bytes() == b'fake audio'
        return Transcript('audio', language, 'speech_to_text', '2026-11-05T00:00:00+00:00', (Segment('Uploaded words', 0, 1),))
    app = create_app(tmp_path/'db', speech_provider=SimpleNamespace(fetch_file=fetch_file), upload_dir=tmp_path/'uploads')
    with TestClient(app) as client:
        result = client.post('/uploads', files={'file': ('recording.wav', b'fake audio', 'audio/wav')}, data={'language':'en'})
        assert result.status_code == 202
        job = wait(client, result.json()['id'])
        assert job['status'] == 'completed'
        assert job['transcript']['source'] == 'speech_to_text'
        assert not seen[0].exists()
        assert 'input_path' not in job


def test_invalid_audio_is_failed_and_deleted(tmp_path):
    app = create_app(tmp_path/'db', upload_dir=tmp_path/'uploads')
    with TestClient(app) as client:
        response = client.post('/uploads', files={'file': ('bad.wav', b'invalid')})
        result = wait(client, response.json()['id'])
        assert result['error']['code'] == 'invalid_audio'
        assert list((tmp_path/'uploads').iterdir()) == []


def test_duration_limit_before_inference(tmp_path):
    import wave
    from youtube_transcriber.audio import decode_bounded
    from youtube_transcriber.models import TranscriptError
    path = tmp_path/'two_seconds.wav'
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b'\0\0' * 32000)
    with pytest.raises(TranscriptError) as error:
        decode_bounded(path, max_seconds=1)
    assert error.value.code == 'audio_too_long'
