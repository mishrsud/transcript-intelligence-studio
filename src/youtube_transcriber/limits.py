"""Bound bodies before multipart parsing can spool unbounded input."""
from tempfile import SpooledTemporaryFile
from starlette.responses import JSONResponse


class BodyLimit:
    def __init__(self, app, max_bytes=201 * 1024 * 1024):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        limit = self.max_bytes if scope['path'] == '/uploads' else 65536
        headers = dict(scope['headers'])
        reject = JSONResponse({'detail': 'Request body is too large'}, status_code=413)
        try:
            if int(headers.get(b'content-length', b'0')) > limit:
                return await reject(scope, receive, send)
        except ValueError:
            return await JSONResponse({'detail': 'Invalid Content-Length'}, status_code=400)(scope, receive, send)
        with SpooledTemporaryFile(max_size=1024 * 1024) as body:
            size = 0
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                chunk = message.get('body', b'')
                size += len(chunk)
                if size > limit:
                    return await reject(scope, receive, send)
                body.write(chunk)
                if not message.get('more_body', False):
                    break
            body.seek(0)
            async def replay():
                chunk = body.read(1024 * 1024)
                return {'type': 'http.request', 'body': chunk, 'more_body': body.tell() < size}
            await self.app(scope, replay, send)
