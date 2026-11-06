"""Explicit test-only identity provider. Production has no authentication bypass."""
import time
from types import SimpleNamespace
from fastapi.testclient import TestClient as BaseClient
from youtube_transcriber.api import create_app as real_create_app
from youtube_transcriber.auth import AuthSettings

class FakeAuth:
    configured = True
    settings = AuthSettings('https://example.kinde.com', 'client', 'test-secret', 'http://testserver', 'youtube-transcriber')
    user_id = 'test-user'

    async def identity(self, request):
        return {'id':self.user_id, 'name':'Test User'}, time.time()+3600


def create_app(*args, **kwargs):
    return real_create_app(*args, auth=FakeAuth(), **kwargs)


class TestClient(BaseClient):
    __test__ = False
    def __enter__(self):
        super().__enter__()
        self.get('/auth/callback', follow_redirects=False)
        self.headers['X-CSRF-Token'] = self.get('/auth/session').json()['csrf_token']
        return self
