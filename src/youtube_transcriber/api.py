from __future__ import annotations

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
from .ai_models import StrictModel
from .email_service import EmailNotConfigured, SMTPEmailSender
from pydantic import ConfigDict, field_validator
import re


class Request(BaseModel):
    url: str = Field(max_length=2048)
    language: str = Field(default='en', pattern=r'^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$', max_length=35)


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    recipient: str = Field(min_length=3, max_length=254)
    content: Literal['transcript', 'insights', 'both']
    insights: EmailInsights | None = None

    @field_validator('recipient')
    @classmethod
    def valid_recipient(cls, value):
        value = value.strip()
        pattern = r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$"
        if not re.fullmatch(pattern, value) or '..' in value or value.split('@', 1)[1].startswith('.') or value.split('@', 1)[1].endswith('.'):
            raise ValueError('Enter one valid email address.')
        return value


class EmailKeyInsight(StrictModel):
    text: str = Field(min_length=1, max_length=1500)
    segment_index: int = Field(ge=0)
    start: float = Field(ge=0)


class EmailActionItem(StrictModel):
    action: str = Field(min_length=1, max_length=1500)
    owner: str | None
    due_date: str | None
    segment_index: int = Field(ge=0)
    start: float = Field(ge=0)


class EmailInsights(StrictModel):
    summary: str = Field(min_length=1, max_length=4000)
    key_insights: list[EmailKeyInsight] = Field(max_length=20)
    action_items: list[EmailActionItem] = Field(max_length=30)
    provider: Literal['openai', 'anthropic', 'openrouter', 'compatible']
    model: str = Field(min_length=1, max_length=200)


EmailRequest.model_rebuild()


def create_app(db_path=None, provider=None, retry_delay=1, speech_provider=None, upload_dir=None, insight_service=None, auth=None, email_sender=None):
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

    @app.post('/transcripts/{id}/email')
    def email_transcript(id: str, request: EmailRequest, http_request: HTTPRequest):
        job = get(id, http_request)
        if job['status'] != 'completed':
            raise HTTPException(409, 'Complete the transcript before emailing it.')
        if request.content in {'insights', 'both'} and request.insights is None:
            raise HTTPException(422, detail={'code':'insights_required', 'message':'Generate insights before including them in the email.'})
        if request.content == 'transcript' and request.insights is not None:
            raise HTTPException(422, detail={'code':'unexpected_insights', 'message':'Insights are only accepted when selected as email content.'})
        transcript_data = job['transcript']
        segments = transcript_data['segments']
        insights_text = ''
        if request.insights is not None:
            for item in request.insights.key_insights + request.insights.action_items:
                if item.segment_index >= len(segments):
                    raise HTTPException(422, detail={'code':'invalid_insight_reference', 'message':'An insight refers to a transcript segment that is unavailable.'})
            lines = ['Summary', request.insights.summary, '', 'Key insights']
            lines.extend(f"- {item.text} [{_format_email_time(segments[item.segment_index]['start'])}]" for item in request.insights.key_insights)
            lines.extend(['', 'Action items'])
            if request.insights.action_items:
                lines.extend(f"- {item.action}{' — Owner: ' + item.owner if item.owner else ''}{' — Due: ' + item.due_date if item.due_date else ''} [{_format_email_time(segments[item.segment_index]['start'])}]" for item in request.insights.action_items)
            else:
                lines.append('No explicit action items found.')
            insights_text = '\n'.join(lines)
        video_url = f"https://www.youtube.com/watch?v={transcript_data['video_id']}"
        body_parts = []
        if request.content in {'insights', 'both'}:
            body_parts.append(insights_text)
        body_parts.extend(['', f"Transcript: {video_url}", f"Sent from Intelligence Studio · {transcript_data['video_id']}"])
        attachment = None
        filename = None
        if request.content in {'transcript', 'both'}:
            data = transcript_data.copy()
            data['segments'] = tuple(Segment(**segment) for segment in data['segments'])
            transcript = Transcript(**data)
            attachment = render(transcript, 'txt')
            if len(attachment.encode('utf-8')) > 5 * 1024 * 1024:
                raise HTTPException(413, detail={'code':'email_attachment_too_large', 'message':'The transcript is too large to attach to an email.'})
            filename = f"{transcript.video_id}.txt"
        try:
            sender = email_sender or SMTPEmailSender()
            sender.send(recipient=request.recipient, subject=f"Intelligence Studio · {transcript_data['video_id']}", body='\n'.join(body_parts).strip(), attachment=attachment, filename=filename)
        except EmailNotConfigured:
            raise HTTPException(503, detail={'code':'smtp_not_configured', 'message':'Email sending is not configured. Add SMTP settings and restart the app.'}) from None
        except Exception:
            raise HTTPException(502, detail={'code':'email_submission_uncertain', 'message':'The SMTP server did not confirm submission. Check the recipient before retrying.'}) from None
        return JSONResponse({'status':'sent'}, headers={'Cache-Control':'no-store'})

    frontend = Path(os.getenv('TRANSCRIBER_FRONTEND', 'frontend/dist'))
    if frontend.is_dir():
        app.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')
    return app


def _format_email_time(seconds):
    whole = int(seconds)
    return f'{whole // 60:02d}:{whole % 60:02d}'


app = create_app()
