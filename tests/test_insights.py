import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from auth_helpers import TestClient, create_app

from youtube_transcriber.store import Store
from youtube_transcriber.insights import InsightService, InsightError, InsightRequest
from youtube_transcriber.ai_transport import public_destination

TRANSCRIPT = {'segments': [{'text': 'We should test the launch. Sam will send a report on Friday.', 'start': 12.5, 'duration': 6}], 'language':'en'}
OUTPUT = {'summary': 'The team plans a launch test.', 'key_insights': [{'text':'The launch needs testing.', 'segment_index':0}], 'action_items': [{'action':'Send the report.', 'owner':'Sam', 'due_date':'Friday', 'segment_index':0}]}
KEY = 'test-secret-do-not-persist'


def response(provider):
    if provider == 'openai':
        return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(OUTPUT)}]}]}
    if provider == 'anthropic':
        return {'stop_reason':'tool_use','content':[{'type':'tool_use','name':'extract_insights','input':OUTPUT}]}
    return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(OUTPUT)}}]}


@pytest.mark.parametrize('provider', ['openai','anthropic','openrouter','compatible'])
def test_provider_payload_and_normalization(provider):
    post = Mock(return_value=(200,response(provider)))
    request = InsightRequest(provider=provider, model='test-model', base_url='https://example.com/v1' if provider == 'compatible' else None)
    result = InsightService(post=post).generate(TRANSCRIPT, request, KEY)
    assert result['key_insights'][0]['start'] == 12.5
    assert result['action_items'][0]['owner'] == 'Sam'
    url, headers, payload = post.call_args.args
    assert KEY not in json.dumps(payload)
    assert KEY not in url
    assert 'transcript' in json.dumps(payload).lower()
    if provider == 'openai':
        assert payload['store'] is False
        assert url == 'https://api.openai.com/v1/responses'
    elif provider == 'anthropic':
        assert headers['x-api-key'] == KEY
        assert payload['tool_choice']['name'] == 'extract_insights'
    else:
        assert url.endswith('/chat/completions')
        assert payload['response_format']['type'] == 'json_object'


@pytest.mark.parametrize('status,code', [(401,'ai_auth'),(403,'ai_auth'),(429,'ai_rate_limit'),(402,'ai_quota'),(500,'ai_unavailable'),(400,'ai_request'),(302,'ai_redirect')])
def test_provider_errors_are_sanitized(status,code):
    with pytest.raises(InsightError) as error:
        InsightService(post=Mock(return_value=(status, {'error':KEY}))).generate(TRANSCRIPT, InsightRequest(provider='openai',model='test'), KEY)
    assert error.value.code == code
    assert KEY not in str(error.value)


def test_invalid_citation_is_rejected():
    bad = json.loads(json.dumps(OUTPUT))
    bad['key_insights'][0]['segment_index'] = 10
    payload = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(bad)}}]}
    with pytest.raises(InsightError, match='valid structured'):
        InsightService(post=Mock(return_value=(200,payload))).generate(TRANSCRIPT, InsightRequest(provider='openrouter',model='test'), KEY)


def test_oversized_transcript_does_not_send_partial_summary():
    post = Mock()
    with pytest.raises(InsightError) as error:
        InsightService(post=post).generate({'segments':[{'text':'a'*120001,'start':0,'duration':1}], 'language':'en'}, InsightRequest(provider='openai',model='test'), KEY)
    assert error.value.code == 'transcript_too_long'
    post.assert_not_called()


@pytest.mark.parametrize('url', ['http://example.com/v1', 'https://user:password@example.com/v1', 'https://example.com/v1?key=abc', 'https://example.com/#fragment'])
def test_unsafe_endpoint_syntax(url):
    with pytest.raises(InsightError):
        public_destination(url)


def test_private_addresses_blocked(monkeypatch):
    monkeypatch.setattr('youtube_transcriber.ai_transport.socket.getaddrinfo', lambda *a, **kw: [(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(InsightError):
        public_destination('https://internal.example/v1')


def test_api_key_not_saved_or_returned(tmp_path, caplog):
    service = InsightService(post=Mock(return_value=(200,response('openai'))))
    store = Store(tmp_path/'db')
    id = store.create('dQw4w9WgXcQ','en', owner_id='test-user')
    store.finish(id, transcript=TRANSCRIPT)
    app = create_app(tmp_path/'db', insight_service=service)
    with TestClient(app) as client:
        r = client.post(f'/transcripts/{id}/insights', headers={'X-AI-API-Key':KEY}, json={'provider':'openai','model':'test'})
        assert r.status_code == 200
        assert r.headers['cache-control'] == 'no-store'
        assert r.json()['summary'] == OUTPUT['summary']
        assert KEY not in r.text
        assert KEY not in json.dumps(app.state.store.get(id))
        assert client.post(f'/transcripts/{id}/insights', json={'provider':'openai','model':'test'}).status_code == 400
    assert KEY not in caplog.text
    assert KEY.encode() not in (tmp_path/'db').read_bytes()


def test_pinned_tls_transport_does_not_redirect_or_retry(monkeypatch):
    from youtube_transcriber.ai_transport import _post_json as post_json
    monkeypatch.setattr('youtube_transcriber.ai_transport.socket.getaddrinfo', lambda *a, **kw: [(2,1,6,'',('8.8.8.8',443))])
    response = Mock(status=200)
    response.read.return_value = b'{"ok":true}'
    pool = Mock()
    pool.urlopen.return_value = response
    factory = Mock(return_value=pool)
    monkeypatch.setattr('youtube_transcriber.ai_transport.urllib3.HTTPSConnectionPool',factory)
    assert post_json('https://api.example.com/v1/test',{'Authorization':'Bearer '+KEY},{'input':'hello'}) == (200,{'ok':True})
    assert factory.call_args.args == ('8.8.8.8',)
    assert factory.call_args.kwargs['server_hostname'] == 'api.example.com'
    assert factory.call_args.kwargs['assert_hostname'] == 'api.example.com'
    assert factory.call_args.kwargs['cert_reqs'] == 'CERT_REQUIRED'
    assert pool.urlopen.call_args.kwargs['redirect'] is False
    assert pool.urlopen.call_args.kwargs['retries'] is False
    assert pool.urlopen.call_args.kwargs['headers']['Host'] == 'api.example.com'
    response.close.assert_called_once()
    pool.close.assert_called_once()


def test_timeout_is_sanitized(monkeypatch):
    import urllib3
    from youtube_transcriber.ai_transport import _post_json as post_json
    monkeypatch.setattr('youtube_transcriber.ai_transport.socket.getaddrinfo', lambda *a, **kw: [(2,1,6,'',('8.8.8.8',443))])
    pool = Mock()
    pool.urlopen.side_effect = urllib3.exceptions.ReadTimeoutError(None, '/', KEY)
    monkeypatch.setattr('youtube_transcriber.ai_transport.urllib3.HTTPSConnectionPool',Mock(return_value=pool))
    with pytest.raises(InsightError) as error:
        post_json('https://api.example.com/v1',{}, {})
    assert error.value.code == 'ai_timeout'
    assert KEY not in str(error.value)


@pytest.mark.parametrize('payload,code', [({'status':'incomplete','output':[]},'ai_incomplete'), ({'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'no'}]}]},'ai_refusal'), ({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'not JSON'}]}]},'ai_response_invalid')])
def test_incomplete_refused_and_malformed_results(payload,code):
    with pytest.raises(InsightError) as error:
        InsightService(post=Mock(return_value=(200,payload))).generate(TRANSCRIPT, InsightRequest(provider='openai',model='test'),KEY)
    assert error.value.code == code


def test_whole_provider_operation_has_hard_deadline(monkeypatch):
    import subprocess
    from youtube_transcriber.ai_transport import post_json
    monkeypatch.setattr('youtube_transcriber.ai_transport.public_destination', lambda _: ('api.example.com',443,'8.8.8.8','/v1'))
    response = Mock(status=200)
    response.read.return_value = b'{}'
    pool = Mock()
    pool.urlopen.return_value = response
    monkeypatch.setattr('youtube_transcriber.ai_transport.urllib3.HTTPSConnectionPool',Mock(return_value=pool))
    run = Mock(side_effect=subprocess.TimeoutExpired('worker',100))
    monkeypatch.setattr(subprocess,'run',run)
    with pytest.raises(InsightError) as error:
        post_json('https://api.example.com/v1',{'Authorization':KEY},{})
    assert error.value.code == 'ai_timeout'
    assert run.call_args.kwargs['timeout'] == 100
    assert KEY not in ' '.join(run.call_args.args[0])
