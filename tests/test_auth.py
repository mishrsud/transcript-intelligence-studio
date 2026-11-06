from fastapi.testclient import TestClient
import time
from youtube_transcriber.api import create_app
from youtube_transcriber.store import Store


def test_unconfigured_auth_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv('KINDE_CLIENT_SECRET', raising=False)
    with TestClient(create_app(tmp_path/'db')) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/auth/session').json()['configured'] is False
        assert client.post('/transcripts', json={'url':'https://youtu.be/jNQXAC9IVRw'}).status_code == 503
        assert client.post('/uploads', content=b'invalid multipart').status_code == 503
        assert client.get('/transcripts/unknown').status_code == 503


def test_caption_cache_is_private(tmp_path):
    store = Store(tmp_path/'db')
    alice = store.create('jNQXAC9IVRw', 'en', owner_id='alice')
    bob = store.create('jNQXAC9IVRw', 'en', owner_id='bob')
    assert alice != bob
    assert store.create('jNQXAC9IVRw', 'en', owner_id='alice') == alice
    assert store.get_owned(alice, 'bob') is None
    assert store.get_owned(alice, 'alice')['id'] == alice
    legacy = store.create('dQw4w9WgXcQ', 'en')
    assert store.get_owned(legacy, 'alice') is None


def test_authorization_csrf_and_ownership(tmp_path):
    from auth_helpers import FakeAuth
    auth = FakeAuth()
    app = create_app(tmp_path/'db', auth=auth)
    with TestClient(app) as client:
        assert client.get('/transcripts/missing').status_code == 401
        assert client.post('/uploads', content=b'not multipart').status_code == 401
        client.get('/auth/callback', follow_redirects=False)
        session = client.get('/auth/session').json()
        assert session['user']['id'] == 'test-user'
        assert 'HttpOnly' in client.get('/auth/callback', follow_redirects=False).headers['set-cookie']
        csrf = client.get('/auth/session').json()['csrf_token']
        own = app.state.store.create('jNQXAC9IVRw', 'en', owner_id='test-user')
        other = app.state.store.create('jNQXAC9IVRw', 'en', owner_id='other-user')
        assert client.get('/transcripts/'+own).status_code == 200
        for suffix in ['', '/export']:
            assert client.get('/transcripts/'+other+suffix).status_code == 404
        assert client.post('/uploads', content=b'not multipart').status_code == 403
        client.headers['X-CSRF-Token'] = csrf
        assert client.post('/uploads', headers={'Origin':'https://evil.example'}, content=b'bad').status_code == 403
        assert client.post('/transcripts/'+other+'/insights', json={'provider':'openai','model':'test'}).status_code == 404
        old_cookie = client.cookies.get('transcript_session')
        assert client.post('/auth/logout').status_code == 200
        client.cookies.set('transcript_session', old_cookie)
        assert client.get('/transcripts/'+own).status_code == 401


def test_authenticated_user_without_permissions_can_use_features(tmp_path):
    from auth_helpers import FakeAuth
    from youtube_transcriber.models import Transcript, Segment
    auth = FakeAuth()
    calls = []
    def fetch(video, language):
        return Transcript(video, language, 'manual', '2026-11-06T00:00:00+00:00', (Segment('Hello', 0, 1),))
    class Speech:
        def fetch_file(self, path, language):
            return Transcript('uploaded', language, 'speech_to_text', '2026-11-06T00:00:00+00:00', (Segment('Uploaded', 0, 1),))
    class Insights:
        def generate(self, transcript, request, key):
            calls.append(transcript['video_id'])
            return {'summary':'summary','insights':[],'actions':[]}
    with TestClient(create_app(tmp_path/'db', provider=type('Provider', (), {'fetch':staticmethod(fetch)})(), speech_provider=Speech(), insight_service=Insights(), auth=auth)) as client:
        client.get('/auth/callback', follow_redirects=False)
        session = client.get('/auth/session').json()
        client.headers['X-CSRF-Token'] = session['csrf_token']
        caption = client.post('/transcripts', json={'url':'https://youtu.be/jNQXAC9IVRw'})
        assert caption.status_code == 202
        upload = client.post('/uploads', files={'file':('recording.wav',b'fixture-audio','audio/wav')})
        assert upload.status_code == 202
        for job in [caption.json()['id'], upload.json()['id']]:
            for _ in range(200):
                result = client.get('/transcripts/'+job).json()
                if result['status'] in {'completed','failed'}:
                    break
                time.sleep(.01)
            assert result['status'] == 'completed'
            assert client.post('/transcripts/'+job+'/insights', json={'provider':'openai','model':'test'}).status_code == 200
        assert calls == ['jNQXAC9IVRw', 'uploaded']
        assert client.get('/transcripts/'+caption.json()['id']+'/export').status_code == 200


def test_anonymous_feature_access_is_blocked(tmp_path):
    from auth_helpers import FakeAuth
    auth = FakeAuth()
    with TestClient(create_app(tmp_path/'db', auth=auth)) as client:
        assert client.post('/transcripts', json={'url':'https://youtu.be/jNQXAC9IVRw'}).status_code == 401
        assert client.post('/uploads', files={'file':('recording.wav',b'x','audio/wav')}).status_code == 401
        assert client.post('/transcripts/unknown/insights', json={'provider':'openai','model':'test'}).status_code == 401


import pytest

@pytest.fixture
def oidc(tmp_path, monkeypatch):
    """Real OAuth exchange/crypto against a deterministic synthetic Kinde server."""
    import base64
    import hashlib
    import json
    import time
    from urllib.parse import parse_qs, urlsplit
    from cryptography.hazmat.primitives.asymmetric import rsa
    import httpx2 as httpx
    import jwt
    from youtube_transcriber.auth import AuthSettings, KindeAuth
    settings = AuthSettings('https://example.kinde.com','client','secret','http://testserver','youtube-transcriber')
    auth = KindeAuth(settings)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {'kid':'test-key','use':'sig','alg':'RS256'}
    jwks = {'keys':[jwk]}
    state = {'nonce':'', 'challenge':'', 'access_changes':{}, 'id_changes':{}, 'calls':0}
    def handle(request):
        if request.url.path.endswith('openid-configuration'):
            return httpx.Response(200,json={'issuer':settings.domain,'authorization_endpoint':settings.domain+'/oauth2/auth','token_endpoint':settings.domain+'/oauth2/token','jwks_uri':settings.domain+'/.well-known/jwks','id_token_signing_alg_values_supported':['RS256']})
        if request.url.path.endswith('/jwks'):
            return httpx.Response(200,json=jwks)
        assert request.url.path == '/oauth2/token'
        state['calls'] += 1
        form = parse_qs(request.content.decode())
        assert form['client_secret'] == ['secret']
        assert form['redirect_uri'] == ['http://testserver/auth/callback']
        challenge = base64.urlsafe_b64encode(hashlib.sha256(form['code_verifier'][0].encode()).digest()).rstrip(b'=').decode()
        assert challenge == state['challenge']
        claims = {'iss':settings.domain,'sub':'alice','aud':settings.audience,'iat':int(time.time()),'exp':int(time.time())+300}
        access = jwt.encode(claims | state['access_changes'], key, algorithm='RS256', headers={'kid':'test-key'})
        id_claims = claims | {'aud':'client', 'nonce':state['nonce'], 'name':'Alice'} | state['id_changes']
        id_token = jwt.encode(id_claims, key, algorithm='RS256', headers={'kid':'test-key'})
        return httpx.Response(200,json={'access_token':access,'id_token':id_token,'token_type':'Bearer','expires_in':300})
    auth.client.client_kwargs['transport'] = httpx.MockTransport(handle)
    monkeypatch.setattr(auth.jwks, 'fetch_data', lambda: jwks)
    with TestClient(create_app(tmp_path/'db',auth=auth)) as client:
        response = client.get('/auth/login', follow_redirects=False)
        assert response.status_code == 302
        query = parse_qs(urlsplit(response.headers['location']).query)
        assert query['code_challenge_method'] == ['S256']
        assert query['audience'] == [settings.audience]
        state.update(nonce=query['nonce'][0], challenge=query['code_challenge'][0], oauth_state=query['state'][0])
        yield client, state, auth


def test_real_oidc_flow_and_replay(oidc):
    client, state, auth = oidc
    before = client.cookies.get('transcript_session')
    url = '/auth/callback?code=synthetic-code&state='+state['oauth_state']
    response = client.get(url, follow_redirects=False)
    assert response.headers['location'] == 'http://testserver/'
    assert client.cookies.get('transcript_session') != before
    info = client.get('/auth/session').json()
    assert info['user']['id'] == 'alice'
    assert info['user'] == {'id':'alice','name':'Alice'}
    assert 'access_token' not in info and 'id_token' not in info
    assert client.get(url, follow_redirects=False).headers['location'].endswith('login_failed')
    assert state['calls'] == 1


@pytest.mark.parametrize('kind,changes', [
    ('access_changes', {'iss':'https://evil.example'}),
    ('access_changes', {'aud':'other-api'}),
    ('access_changes', {'exp':1}),
    ('access_changes', {'sub':'mallory'}),
    ('id_changes', {'nonce':'wrong-nonce'}),
    ('id_changes', {'aud':'other-client'}),
    ('id_changes', {'iss':'https://evil.example'}),
])
def test_rejects_invalid_tokens(oidc, kind, changes):
    client, state, auth = oidc
    state[kind] = changes
    response = client.get('/auth/callback?code=test&state='+state['oauth_state'], follow_redirects=False)
    assert response.headers['location'].endswith('login_failed')
    assert client.get('/auth/session').json()['user'] is None


def test_rejects_id_token_wrong_audience_even_with_authorized_party(oidc):
    client, state, auth = oidc
    state['id_changes'] = {'aud':'other-client','azp':auth.settings.client_id}
    response = client.get('/auth/callback?code=test&state='+state['oauth_state'], follow_redirects=False)
    assert response.headers['location'].endswith('login_failed')
    assert client.get('/auth/session').json()['user'] is None


def test_accepts_id_token_audience_array_containing_client_and_azp(oidc):
    client, state, auth = oidc
    state['id_changes'] = {'aud':['other-client', auth.settings.client_id], 'azp':auth.settings.client_id}
    response = client.get('/auth/callback?code=test&state='+state['oauth_state'], follow_redirects=False)
    assert response.headers['location'] == 'http://testserver/'
    assert client.get('/auth/session').json()['user']['id'] == 'alice'


def test_rejects_wrong_state_without_token_exchange(oidc):
    client, state, auth = oidc
    assert client.get('/auth/callback?code=test&state=wrong', follow_redirects=False).headers['location'].endswith('login_failed')
    assert state['calls'] == 0


def test_rejects_forged_signature(oidc):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    client, state, auth = oidc
    forged = jwt.encode({'iss':auth.settings.domain,'sub':'alice','aud':auth.settings.audience,'exp':9999999999,'iat':1}, rsa.generate_private_key(public_exponent=65537,key_size=2048), algorithm='RS256', headers={'kid':'test-key'})
    with pytest.raises(jwt.InvalidSignatureError):
        auth.verify_access_token(forged)


def test_expired_session_cannot_access_jobs(tmp_path, monkeypatch):
    import time
    from auth_helpers import FakeAuth
    now = time.time()
    with TestClient(create_app(tmp_path/'db', auth=FakeAuth())) as client:
        client.get('/auth/callback', follow_redirects=False)
        assert client.get('/auth/session').json()['user'] is not None
        monkeypatch.setattr('youtube_transcriber.sessions.time.time', lambda: now+3601)
        assert client.get('/auth/session').json()['user'] is None
        response = client.get('/transcripts/anything')
        assert response.status_code == 401
        assert response.headers['X-Session-Expired'] == '1'


def test_https_session_cookie_is_secure(tmp_path):
    from dataclasses import replace
    from auth_helpers import FakeAuth
    auth = FakeAuth()
    auth.settings = replace(auth.settings, public_url='https://testserver')
    with TestClient(create_app(tmp_path/'db',auth=auth), base_url='https://testserver') as client:
        response = client.get('/auth/callback',follow_redirects=False)
        cookie = response.headers['set-cookie']
        assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=lax' in cookie
        assert client.get('/auth/session').json()['user'] is not None


def test_remote_insecure_origin_is_rejected(monkeypatch):
    from youtube_transcriber.auth import AuthSettings
    monkeypatch.setenv('APP_URL','http://public.example')
    with pytest.raises(ValueError):
        AuthSettings.from_env()


def test_callback_failure_logs_type_without_secrets(tmp_path, caplog):
    from auth_helpers import FakeAuth
    from authlib.integrations.base_client.errors import MismatchingStateError
    class FailingAuth(FakeAuth):
        async def identity(self, request):
            raise MismatchingStateError(description='secret-code-and-token-do-not-log')
    with TestClient(create_app(tmp_path/'db', auth=FailingAuth())) as client:
        response = client.get('/auth/callback?code=secret-code-and-token-do-not-log', follow_redirects=False)
        assert response.status_code == 303
        assert 'MismatchingStateError' in caplog.text
        assert 'secret-code-and-token-do-not-log' not in caplog.text
        assert 'secret-code-and-token-do-not-log' not in response.headers['location']
