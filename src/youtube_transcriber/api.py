from contextlib import asynccontextmanager
import os
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request as HTTPRequest
from uuid import uuid4
from .audio import LocalSpeechProvider
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dotenv import load_dotenv
from .auth import AuthSettings, KindeAuth, install_routes
from .sessions import AuthBoundary

load_dotenv()

from .exports import render
from .models import Segment, Transcript, TranscriptError
from .provider import YouTubeCaptionProvider
from .store import Store
from .urls import parse_url
from .worker import Worker
from .limits import BodyLimit
from .insights import InsightService, InsightRequest, InsightError


class Request(BaseModel):
    url: str = Field(max_length=2048)
    language: str = Field(default='en', pattern=r'^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$', max_length=35)


def create_app(db_path=None, provider=None, retry_delay=1, speech_provider=None, upload_dir=None, insight_service=None, auth=None):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s level=%(levelname)s logger=%(name)s %(message)s')
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(db_path or os.getenv('TRANSCRIBER_DB', 'data/transcripts.db'))
        worker = Worker(app.state.store, provider or YouTubeCaptionProvider(), retry_delay, speech_provider or LocalSpeechProvider())
        worker.start()
        yield
        worker.close()

    app = FastAPI(title='YouTube Transcriber', lifespan=lifespan)
    app.add_middleware(BodyLimit)
    auth = auth or KindeAuth(AuthSettings.from_env())
    install_routes(app, auth)
    app.add_middleware(AuthBoundary, auth=auth)

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.post('/transcripts', status_code=202)
    def submit(request: Request, http_request: HTTPRequest):
        try:
            video_id = parse_url(request.url)
        except TranscriptError as exc:
            raise HTTPException(422, detail={'code': exc.code, 'message': str(exc)}) from exc
        id = app.state.store.create(video_id, request.language.lower(), owner_id=http_request.state.user['id'])
        return {'id': id}

    @app.post('/uploads', status_code=202)
    async def upload(http_request: HTTPRequest, file: UploadFile = File(...), language: str = Form('en', pattern=r'^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$', max_length=35)):
        directory = Path(upload_dir or os.getenv('TRANSCRIBER_UPLOAD_DIR', 'data/uploads'))
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / uuid4().hex
        try:
            size = 0
            with path.open('xb') as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 200 * 1024 * 1024:
                        raise HTTPException(413, 'Files must be 200 MB or smaller')
                    output.write(chunk)
            if size == 0:
                raise HTTPException(422, 'The uploaded file is empty')
            id = app.state.store.create_audio(path, language.lower(), owner_id=http_request.state.user['id'])
            return {'id': id}
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @app.get('/transcripts/{id}')
    def get(id: str, http_request: HTTPRequest):
        job = app.state.store.get_owned(id, http_request.state.user['id'])
        if job is None:
            raise HTTPException(404, 'Transcript job not found')
        job.pop('input_path', None)
        job.pop('owner_id', None)
        return job

    @app.get('/transcripts/{id}/export')
    def export(id: str, http_request: HTTPRequest, format: Literal['txt', 'srt', 'json'] = 'txt'):
        job = get(id, http_request)
        if job['status'] != 'completed':
            raise HTTPException(409, 'Transcript is not ready')
        data = job['transcript'].copy()
        data['segments'] = tuple(Segment(**s) for s in data['segments'])
        transcript = Transcript(**data)
        return Response(render(transcript, format), media_type='application/json' if format == 'json' else 'text/plain', headers={'Content-Disposition': f'attachment; filename="{transcript.video_id}.{format}"'})

    @app.post('/transcripts/{id}/insights')
    def insights(id: str, request: InsightRequest, http_request: HTTPRequest):
        job = get(id, http_request)
        if job['status'] != 'completed':
            raise HTTPException(409, 'Complete the transcript before generating insights', headers={'Cache-Control':'no-store'})
        try:
            result = (insight_service or InsightService()).generate(job['transcript'], request, http_request.headers.get('X-AI-API-Key', ''))
            return JSONResponse(result, headers={'Cache-Control':'no-store'})
        except InsightError as exc:
            raise HTTPException(exc.status, detail={'code':exc.code, 'message':str(exc)}, headers={'Cache-Control':'no-store'}) from None

    frontend = Path(os.getenv('TRANSCRIBER_FRONTEND', 'frontend/dist'))
    if frontend.is_dir():
        app.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')
    return app


app = create_app()
