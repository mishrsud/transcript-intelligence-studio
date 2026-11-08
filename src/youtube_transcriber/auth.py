"""Kinde OIDC boundary. OAuth tokens never leave the server or enter storage."""
from dataclasses import dataclass
import os
import logging
import secrets
import time
from urllib.parse import urlsplit, urlencode

from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
import jwt
from starlette.concurrency import run_in_threadpool


logger = logging.getLogger(__name__)

def log_auth_failure(stage, exc):
    # Fixed stage and exception class only: exception messages may contain credentials.
    oauth_error = getattr(exc, 'error', '')
    safe_error = oauth_error if oauth_error in {'invalid_client', 'invalid_grant', 'access_denied', 'mismatching_state', 'invalid_token', 'invalid_request'} else 'unspecified'
    logger.warning('Kinde auth failure stage=%s type=%s reason=%s', stage, type(exc).__name__, safe_error)


@dataclass(frozen=True)
class AuthSettings:
    domain: str
    client_id: str
    client_secret: str
    public_url: str
    audience: str

    @classmethod
    def from_env(cls):
        settings = cls(os.getenv('KINDE_DOMAIN', '').rstrip('/'), os.getenv('KINDE_CLIENT_ID', ''),
                       os.getenv('KINDE_CLIENT_SECRET', ''), os.getenv('APP_URL', 'http://127.0.0.1:8000').rstrip('/'),
                       os.getenv('KINDE_AUDIENCE', 'youtube-transcriber'))
        for value, local_allowed in ((settings.domain, False), (settings.public_url, True)):
            if not value:
                continue
            url = urlsplit(value)
            local = local_allowed and url.hostname in {'localhost', '127.0.0.1', '::1'}
            if (url.scheme != 'https' and not (local and url.scheme == 'http')) or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
                raise ValueError('Auth URLs must be HTTPS origins (HTTP allowed only for local APP_URL)')
        return settings

    @property
    def configured(self):
        return bool(self.domain and self.client_id and self.client_secret and self.audience)


class KindeAuth:
    def __init__(self, settings):
        self.settings = settings
        self.configured = settings.configured
        self.client = None
        if self.configured:
            self.client = OAuth().register(
                name='kinde', client_id=settings.client_id, client_secret=settings.client_secret,
                server_metadata_url=settings.domain + '/.well-known/openid-configuration',
                client_kwargs={'scope':'openid profile email', 'code_challenge_method':'S256',
                               'token_endpoint_auth_method':'client_secret_post', 'timeout':15},
            )
            self.jwks = jwt.PyJWKClient(settings.domain + '/.well-known/jwks', timeout=10)

    def verify_access_token(self, token):
        key = self.jwks.get_signing_key_from_jwt(token)
        return jwt.decode(token, key.key, algorithms=['RS256'], issuer=self.settings.domain,
                          audience=self.settings.audience, options={'require':['exp','iat','iss','aud','sub']})

    async def identity(self, request):
        # Authlib validates state, PKCE response, ID-token signature and nonce; client audience is checked below.
        try:
            token = await self.client.authorize_access_token(request)
        except Exception as exc:
            log_auth_failure('code_exchange_or_id_token', exc)
            raise
        user = token.get('userinfo')
        try:
            claims = await run_in_threadpool(self.verify_access_token, token['access_token'])
        except Exception as exc:
            log_auth_failure('access_token', exc)
            raise
        audience = user.get('aud') if user else None
        if isinstance(audience, str):
            client_audience_valid = audience == self.settings.client_id
        elif isinstance(audience, list):
            client_audience_valid = bool(audience) and all(isinstance(value, str) and value for value in audience) and self.settings.client_id in audience
        else:
            client_audience_valid = False
        if (not user or not client_audience_valid or user.get('iss') != self.settings.domain
                or not user.get('sub') or user['sub'] != claims['sub']):
            raise ValueError('Token identity mismatch')
        email = user.get('email')
        if not isinstance(email, str) or len(email) > 254 or any(ord(char) < 32 for char in email):
            email = None
        identity = {'id':user['sub'], 'name':user.get('name') or user.get('given_name') or 'Signed in'}
        if email:
            identity['email'] = email
        return identity, min(float(claims['exp']), float(user['exp']), time.time()+3600)


def install_routes(app, auth):
    def require_config():
        if not auth.configured:
            raise HTTPException(503, 'Kinde is not configured. Follow the README authentication setup.')

    @app.get('/auth/session')
    async def session(request: Request):
        user = request.session.get('user')
        return JSONResponse({'configured':auth.configured, 'user':user,
                             'csrf_token':request.session.get('csrf') if user else None}, headers={'Cache-Control':'no-store'})

    @app.get('/auth/login')
    async def login(request: Request):
        require_config()
        request.session.clear()
        try:
            return await auth.client.authorize_redirect(request, auth.settings.public_url + '/auth/callback', audience=auth.settings.audience)
        except Exception as exc:
            log_auth_failure('login_redirect', exc)
            request.session.clear()
            return RedirectResponse('/?auth_error=unavailable', status_code=303)

    @app.get('/auth/callback')
    async def callback(request: Request):
        require_config()
        try:
            user, expires = await auth.identity(request)
            if expires <= time.time():
                raise ValueError('Expired identity')
            request.session.clear()
            request.session.update(user=user, expires=expires, csrf=secrets.token_urlsafe(32))
            request.state.rotate_session = True
            return RedirectResponse(auth.settings.public_url + '/', status_code=303)
        except Exception as exc:
            log_auth_failure('callback', exc)
            # Never include token, code, provider body or exception message in logs/responses.
            request.session.clear()
            return RedirectResponse(auth.settings.public_url + '/?auth_error=login_failed', status_code=303)

    @app.post('/auth/logout')
    async def logout(request: Request):
        require_config()
        request.session.clear()
        return JSONResponse({'url':auth.settings.domain + '/logout?' + urlencode({'redirect':auth.settings.public_url + '/'})})
