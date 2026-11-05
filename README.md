# Transcript Studio

A personal-use, caption-first YouTube transcriber for your Mac. Paste a watch, Shorts, or youtu.be URL, select a caption language, then read, copy, or download TXT/SRT. Manual captions take priority over automatic captions. If captions are unavailable, upload audio/video for local speech recognition.

## Run on this Mac

Requires Python 3.11+ and Node 22.12+.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,audio]'
npm ci --prefix frontend
npm run build --prefix frontend
.venv/bin/uvicorn youtube_transcriber.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Use one server process: the worker recovers interrupted jobs at startup. Do not run multiple instances against the same database. For UI development, run `npm run dev --prefix frontend` alongside the backend; Vite proxies API requests.

Audio is processed on the CPU using faster-whisper. The first upload downloads the `tiny` model (roughly 75 MB); later uploads reuse the model. Set `TRANSCRIBER_MODEL=base` or `small` for better accuracy at greater memory/processing cost. The app accepts up to 200 MiB and 60 minutes, decodes one audio track, and uses Whisper's internal timestamp-aware windows. Uploaded files are deleted after success or failure. An interrupted job resumes on the next start. Recognition is probabilistic; review important text and timings.

## CLI

```sh
.venv/bin/youtube-transcriber 'https://youtu.be/jNQXAC9IVRw' --language en
.venv/bin/youtube-transcriber 'https://youtu.be/jNQXAC9IVRw' --format srt > /tmp/transcript.srt
```

JSON is the default and preserves `text`, `start`, and `duration`, plus source, language, video ID, and retrieval time. Errors are structured JSON on stderr with exit status 1.

## API

- `POST /transcripts`: JSON `{ "url": "https://youtu.be/…", "language": "en" }`, returns `{ "id": "…" }` (202).
- `GET /transcripts/{id}`: queued, processing, completed or failed; includes transcript or error.
- `GET /transcripts/{id}/export?format=txt`: TXT, SRT or JSON download; 409 before completion.
- `POST /uploads`: multipart `file` and `language`; returns a local speech job ID.
- `GET /health`: health check. Interactive API docs at `/docs`.

Completed caption jobs are cached for 24 hours by video ID and requested language. Temporary network failures get at most three attempts with exponential delay. Missing captions, unavailable language/video and access restrictions are separate errors. Timestamped segments remain the source of truth.

## Verify

```sh
.venv/bin/python -m pytest -q
npm run build --prefix frontend
.venv/bin/python scripts/smoke.py
```

The live smoke test needs the running app and internet access. YouTube behavior and caption availability can change. Test doubles in the offline tests are synthetic unless marked as recorded. See [the implementation plan](docs/plan.md) for live test evidence and remaining limitations.

## Docker

```sh
docker compose up --build -d
```

Open http://127.0.0.1:8001. SQLite, cached transcripts and model files persist in the named volume. `docker compose down` stops the app and retains that volume. This is an unauthenticated personal app; the supplied commands publish only to localhost.

Configuration: `TRANSCRIBER_DB` (default `data/transcripts.db`), `TRANSCRIBER_UPLOAD_DIR` (`data/uploads`), `TRANSCRIBER_MODEL` (`tiny`), `TRANSCRIBER_MODEL_DIR` (`data/models`), `TRANSCRIBER_FRONTEND` (`frontend/dist`). Local runtime data is ignored by Git. Application logs identify job IDs, outcomes and error codes.

## Design references

- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api): isolated behind `CaptionProvider` because YouTube interfaces and IP access can change.
- [Official YouTube caption download API](https://developers.google.com/youtube/data/reference/rest/v3/captions/download): requires permission to edit the video.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): local speech inference and timestamped decoding.

URL-based audio downloading is intentionally outside this version; upload an accessible file when captions are unavailable.
