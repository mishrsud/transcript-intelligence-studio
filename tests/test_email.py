import time
from types import SimpleNamespace

from auth_helpers import TestClient, create_app
from youtube_transcriber.email_service import SMTPEmailSender, SMTPSettings
from youtube_transcriber.models import Segment, Transcript


class Sender:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def send(self, *, recipient, subject, body, attachment=None, filename=None):
        self.calls.append((recipient, subject, body, attachment, filename))
        if self.error:
            raise self.error


def completed_app(tmp_path, sender):
    transcript = Transcript('dQw4w9WgXcQ', 'en', 'manual', '2026-11-05T00:00:00+00:00', (Segment('Hello there', 0, 2),))
    provider = SimpleNamespace(fetch=lambda *_: transcript)
    app = create_app(tmp_path / 'jobs.db', provider, retry_delay=0, email_sender=sender)
    return app


def test_sends_transcript_as_txt_attachment(tmp_path, monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    sender = Sender()
    with TestClient(completed_app(tmp_path, sender)) as client:
        job = client.post('/transcripts', json={'url':'https://youtu.be/dQw4w9WgXcQ'}).json()['id']
        for _ in range(100):
            if client.get(f'/transcripts/{job}').json()['status'] == 'completed':
                break
            time.sleep(.01)
        response = client.post(f'/transcripts/{job}/email', json={'recipient':'person@example.com','content':'transcript'})
        assert response.status_code == 200
        assert response.json() == {'status':'sent'}
    recipient, subject, body, attachment, filename = sender.calls[0]
    assert recipient == 'person@example.com'
    assert subject.startswith('Intelligence Studio')
    assert 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' in body
    assert attachment == 'Hello there\n'
    assert filename.endswith('.txt')


def test_rejects_bad_recipient_and_insight_reference_before_smtp(tmp_path, monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    sender = Sender()
    with TestClient(completed_app(tmp_path, sender)) as client:
        job = client.post('/transcripts', json={'url':'https://youtu.be/dQw4w9WgXcQ'}).json()['id']
        for _ in range(100):
            if client.get(f'/transcripts/{job}').json()['status'] == 'completed':
                break
            time.sleep(.01)
        invalid_email = client.post(f'/transcripts/{job}/email', json={'recipient':'bad\r\nBcc:x@y.test','content':'transcript'})
        assert invalid_email.status_code == 422
        invalid_insights = client.post(f'/transcripts/{job}/email', json={'recipient':'person@example.com','content':'insights','insights':{'summary':'Summary','key_insights':[{'text':'Claim','segment_index':1,'start':9}],'action_items':[],'provider':'openai','model':'x'}})
        assert invalid_insights.status_code == 422
    assert sender.calls == []


def test_smtp_failure_is_safe_and_not_retried(tmp_path, monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    sender = Sender(RuntimeError('secret credential details'))
    with TestClient(completed_app(tmp_path, sender)) as client:
        job = client.post('/transcripts', json={'url':'https://youtu.be/dQw4w9WgXcQ'}).json()['id']
        for _ in range(100):
            if client.get(f'/transcripts/{job}').json()['status'] == 'completed':
                break
            time.sleep(.01)
        response = client.post(f'/transcripts/{job}/email', json={'recipient':'person@example.com','content':'transcript'})
    assert response.status_code == 502
    assert 'secret' not in response.text
    assert len(sender.calls) == 1


def test_insights_and_both_use_ephemeral_content_and_server_timestamps(tmp_path, monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    sender = Sender()
    with TestClient(completed_app(tmp_path, sender)) as client:
        job = client.post('/transcripts', json={'url':'https://youtu.be/dQw4w9WgXcQ'}).json()['id']
        for _ in range(100):
            if client.get(f'/transcripts/{job}').json()['status'] == 'completed':
                break
            time.sleep(.01)
        insights = {'summary':'A short summary.', 'key_insights':[{'text':'A claim.','segment_index':0,'start':999}],
                    'action_items':[],'provider':'openai','model':'model-id'}
        response = client.post(f'/transcripts/{job}/email', json={'recipient':'person@example.com','content':'both','insights':insights})
    assert response.status_code == 200
    _, _, body, attachment, _ = sender.calls[0]
    assert 'A short summary.' in body
    assert '[00:00]' in body
    assert '[16:39]' not in body
    assert attachment == 'Hello there\n'


def test_smtp_missing_configuration_is_reported_without_sending(tmp_path, monkeypatch):
    monkeypatch.delenv('SMTP_HOST', raising=False)
    monkeypatch.delenv('SMTP_FROM_ADDRESS', raising=False)
    with TestClient(completed_app(tmp_path, None)) as client:
        job = client.post('/transcripts', json={'url':'https://youtu.be/dQw4w9WgXcQ'}).json()['id']
        for _ in range(100):
            if client.get(f'/transcripts/{job}').json()['status'] == 'completed':
                break
            time.sleep(.01)
        response = client.post(f'/transcripts/{job}/email', json={'recipient':'person@example.com','content':'transcript'})
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'smtp_not_configured'


def test_email_requires_csrf_and_owner_scoped_job(tmp_path, monkeypatch):
    import time as clock
    from fastapi.testclient import TestClient as BaseClient
    from youtube_transcriber.api import create_app as real_create_app
    from youtube_transcriber.auth import AuthSettings

    class Auth:
        configured = True
        settings = AuthSettings('https://example.kinde.com', 'client', 'secret', 'http://testserver', 'audience')
        user_id = 'first-user'
        async def identity(self, request):
            return {'id':self.user_id, 'name':'User'}, clock.time() + 3600

    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    sender = Sender()
    auth = Auth()
    app = real_create_app(tmp_path/'db.sqlite', provider=SimpleNamespace(fetch=lambda *_: Transcript('dQw4w9WgXcQ', 'en', 'manual', '2026-11-05T00:00:00+00:00', (Segment('Hi', 0, 1),))), retry_delay=0, auth=auth, email_sender=sender)
    with BaseClient(app) as first:
        first.get('/auth/callback', follow_redirects=False)
        first.headers['X-CSRF-Token'] = first.get('/auth/session').json()['csrf_token']
        job = first.post('/transcripts', json={'url':'https://youtu.be/dQw4w9WgXcQ'}).json()['id']
        for _ in range(100):
            if first.get(f'/transcripts/{job}').json()['status'] == 'completed':
                break
            time.sleep(.01)
        csrf = first.headers.pop('X-CSRF-Token')
        no_csrf = first.post(f'/transcripts/{job}/email', json={'recipient':'person@example.com','content':'transcript'})
        first.headers['X-CSRF-Token'] = csrf
        auth.user_id = 'other-user'
        with BaseClient(app) as other:
            other.get('/auth/callback', follow_redirects=False)
            other.headers['X-CSRF-Token'] = other.get('/auth/session').json()['csrf_token']
            not_owner = other.post(f'/transcripts/{job}/email', json={'recipient':'person@example.com','content':'transcript'})
    assert no_csrf.status_code == 403
    assert not_owner.status_code == 404
    assert sender.calls == []


def test_smtp_starttls_precedes_login_and_send(monkeypatch):
    import youtube_transcriber.email_service as email_service
    events = []
    context = object()

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            events.append(('connect', host, port, timeout))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self, *, context): events.append(('starttls', context))
        def login(self, username, password): events.append(('login', username, password))
        def send_message(self, message): events.append(('send', message))

    monkeypatch.setattr(email_service.ssl, 'create_default_context', lambda: context)
    monkeypatch.setattr(email_service.smtplib, 'SMTP', FakeSMTP)
    sender = SMTPEmailSender(SMTPSettings('smtp.example.test', 587, 'account', 'secret', 'studio@example.test', 'starttls'), timeout=9)
    sender.send(recipient='person@example.test', subject='Subject', body='Body', attachment='Transcript', filename='video.txt')
    assert [event[0] for event in events] == ['connect', 'starttls', 'login', 'send']
    assert events[0] == ('connect', 'smtp.example.test', 587, 9)
    assert events[1] == ('starttls', context)
    message = events[-1][1]
    assert message['To'] == 'person@example.test'
    assert message['From'] == 'studio@example.test'
    assert message['Subject'] == 'Subject'
    assert [part.get_filename() for part in message.iter_attachments()] == ['video.txt']


def test_smtp_ssl_uses_secure_context_and_never_falls_back(monkeypatch):
    import youtube_transcriber.email_service as email_service
    events = []
    context = object()

    class FakeSMTPSSL:
        def __init__(self, host, port, *, timeout, context): events.append(('connect_ssl', host, port, timeout, context))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self, **kwargs): events.append(('starttls', kwargs))
        def send_message(self, message): events.append(('send', message))

    monkeypatch.setattr(email_service.ssl, 'create_default_context', lambda: context)
    monkeypatch.setattr(email_service.smtplib, 'SMTP_SSL', FakeSMTPSSL)
    sender = SMTPEmailSender(SMTPSettings('smtp.example.test', 465, '', '', 'studio@example.test', 'ssl'))
    sender.send(recipient='person@example.test', subject='Subject', body='Body')
    assert [event[0] for event in events] == ['connect_ssl', 'send']
    assert events[0] == ('connect_ssl', 'smtp.example.test', 465, 15, context)


def test_starttls_failure_stops_before_auth_or_send(monkeypatch):
    import socket
    import youtube_transcriber.email_service as email_service
    events = []

    class FailingTLS:
        def __init__(self, *args, **kwargs): events.append('connect')
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self, **kwargs):
            events.append('starttls')
            raise socket.timeout('TLS timeout containing secret')
        def login(self, *args): events.append('login')
        def send_message(self, *args): events.append('send')

    monkeypatch.setattr(email_service.smtplib, 'SMTP', FailingTLS)
    sender = SMTPEmailSender(SMTPSettings('smtp.example.test', 587, 'account', 'secret', 'studio@example.test', 'starttls'))
    try:
        sender.send(recipient='person@example.test', subject='Subject', body='Body')
    except socket.timeout:
        pass
    else:
        raise AssertionError('TLS timeout should propagate to the API error boundary')
    assert events == ['connect', 'starttls']


def test_smtp_timeout_is_redacted_and_not_retried_by_endpoint(tmp_path, monkeypatch):
    import socket
    import youtube_transcriber.email_service as email_service
    events = []

    class TimedOutSMTP:
        def __init__(self, *args, **kwargs): events.append('connect')
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self, **kwargs): events.append('starttls')
        def login(self, *args): events.append('login')
        def send_message(self, *args):
            events.append('send')
            raise socket.timeout('timeout after accepted; account-secret=do-not-leak')

    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    monkeypatch.setenv('SMTP_FROM_ADDRESS', 'studio@example.test')
    monkeypatch.setenv('SMTP_USERNAME', 'account')
    monkeypatch.setenv('SMTP_PASSWORD', 'account-secret')
    monkeypatch.setattr(email_service.smtplib, 'SMTP', TimedOutSMTP)
    with TestClient(completed_app(tmp_path, SMTPEmailSender())) as client:
        job = client.post('/transcripts', json={'url':'https://youtu.be/dQw4w9WgXcQ'}).json()['id']
        for _ in range(100):
            if client.get(f'/transcripts/{job}').json()['status'] == 'completed':
                break
            time.sleep(.01)
        response = client.post(f'/transcripts/{job}/email', json={'recipient':'person@example.com','content':'transcript'})
    assert response.status_code == 502
    assert response.json()['detail']['code'] == 'email_submission_uncertain'
    assert 'account-secret' not in response.text
    assert 'accepted' not in response.text
    assert events == ['connect', 'starttls', 'login', 'send']
