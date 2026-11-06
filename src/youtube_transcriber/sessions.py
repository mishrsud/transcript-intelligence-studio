"""Bounded, process-local opaque sessions; restarting the single worker signs out users."""
import copy
import secrets
import time

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

COOKIE = 'transcript_session'


class AuthBoundary(BaseHTTPMiddleware):
    def __init__(self, app, auth):
        super().__init__(app)
        self.auth = auth
        self.sessions = {}

    async def dispatch(self, request, call_next):
        now = time.time()
        # A hard cap also bounds cleanup work. Never evict active sessions to admit a login.
        for key in [k for k, v in self.sessions.items() if v['expires'] <= now]:
            del self.sessions[key]
        sid = request.cookies.get(COOKIE)
        original = self.sessions.get(sid)
        data = copy.deepcopy(original['data']) if original else {}
        request.scope['session'] = data
        path = request.url.path
        protected = path == '/uploads' or path == '/transcripts' or path.startswith('/transcripts/') or path == '/auth/logout'
        error = None
        if protected:
            user = data.get('user')
            if not self.auth.configured:
                error = (503, 'Kinde is not configured. Follow the README authentication setup.')
            elif not user:
                error = (401, 'Sign in to continue.')
            elif request.method not in {'GET', 'HEAD', 'OPTIONS'} and (
                not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), data.get('csrf', ''))
                or not data.get('csrf')
                or (request.headers.get('origin') and request.headers['origin'] != self.auth.settings.public_url)
            ):
                error = (403, 'The session could not verify this request. Refresh and try again.')
            if not error:
                request.state.user = user
        if error:
            return JSONResponse({'detail':error[1]}, status_code=error[0], headers={'Cache-Control':'no-store', **({'X-Session-Expired':'1'} if error[0] == 401 else {})})
        response = await call_next(request)
        if protected or path.startswith('/auth/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        if not data:
            self.sessions.pop(sid, None)
            if sid:
                response.delete_cookie(COOKIE, path='/')
        elif data != (original['data'] if original else {}) or getattr(request.state, 'rotate_session', False):
            # Only modify an existing session if a parallel logout has not invalidated it.
            if original is not None and self.sessions.get(sid) is not original:
                return response
            rotate = original is None or getattr(request.state, 'rotate_session', False)
            if rotate:
                self.sessions.pop(sid, None)
                if len(self.sessions) >= 10000:
                    return JSONResponse({'detail':'Too many sessions. Try again later.'}, status_code=503)
                sid = secrets.token_urlsafe(32)
            expires = data.get('expires', original['expires'] if original else now + 600)
            self.sessions[sid] = {'expires':expires, 'data':copy.deepcopy(data)}
            response.set_cookie(COOKIE, sid, max_age=max(1, int(expires-now)), httponly=True,
                                secure=self.auth.settings.public_url.startswith('https://'), samesite='lax', path='/')
        return response
