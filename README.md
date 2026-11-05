# Transcript Studio

A personal-use, caption-first YouTube transcriber for your Mac. Paste a watch, Shorts, or youtu.be URL, select a caption language, then read, copy, or download TXT/SRT. Manual captions take priority over automatic captions. If captions are unavailable, upload audio/video for local speech recognition.

## Build and launch locally

Requires **Python 3.11+** and **Node.js 22.12+ with npm** on macOS or Linux. Docker is not required for this option.

From the repository root:

```sh
python3 build/run.py
```

The script creates `.venv` if needed, builds and installs the Python backend with local audio support, installs the locked frontend dependencies, builds the React frontend, and starts the app at **http://127.0.0.1:8000**. After the health check succeeds, it opens your default browser. FastAPI serves both the built frontend and API, so only one server process is needed. Keep the terminal open; **Ctrl+C** stops the app and its child process. Dependencies require internet on first installation.

Options:

```sh
python3 build/run.py --port 8080       # Use another local port
python3 build/run.py --no-browser      # Start without opening a browser (e.g. SSH)
python3 build/run.py --help
```

You can also invoke the script by absolute path from another directory. It always resolves paths relative to the repository. An occupied port is reported without stopping the existing service. Each invocation rebuilds the current source. Use one app instance per database; do not start a second native instance on another port against the same database. The Docker deployment uses a separate named volume.

The UI uses a Google Cloud Console-inspired layout with **dark mode by default**. Use the sun/moon button in the top-right corner to switch themes; your choice is remembered in that browser. If browser storage is disabled, the toggle still works for the current visit.

### Manual development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,audio]'
npm ci --prefix frontend
.venv/bin/uvicorn youtube_transcriber.api:app --host 127.0.0.1 --port 8000
```

In another terminal, run `npm run dev --prefix frontend` for the Vite development server with hot reload and API proxying. Alternatively, `npm run build --prefix frontend` creates production assets for the backend to serve. After using the launcher, reinstall with `pip install -e '.[dev,audio]'` before editing Python source for live development: the launcher installs a built package, not an editable checkout.

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
npm test --prefix frontend
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


## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on pushes, pull requests, and manual dispatch. It tests Python 3.11/3.12, builds the backend wheel, runs frontend component tests and the TypeScript/Vite production build, then builds and starts the Docker image to check the API and frontend. Tests use fixtures and do not contact YouTube or download speech models. The workflow does not deploy or publish images. It will run once this repository is pushed to GitHub with Actions enabled.

## Hosting options

Recommendations checked against provider documentation on 5 November 2026. For the current architecture, use **one always-running instance with persistent storage** for SQLite, uploads and model files. Start with roughly 2 vCPU and 4 GB RAM for occasional CPU speech recognition, then measure your recordings; this is a sizing recommendation, not a benchmark.

| Option | Fit for this app | What to plan for |
| --- | --- | --- |
| This Mac | Best personal-use starting point; caption retrieval and speech recognition are already verified here | Mac must remain awake and running; keep access local or behind a private network |
| Render paid Docker web service + persistent disk | My recommendation for a managed first deployment with minimal architecture changes | Mount the disk at `/app/data`, keep one instance, and select enough CPU/RAM for speech; free services cannot attach persistent disks. [Disk documentation](https://render.com/docs/disks) |
| Fly.io Machine + volume | Good fit for the existing Docker image and SQLite | Mount a volume at `/app/data`, keep the worker's machine running, and configure backups; volumes attach to a single machine and are not automatically replicated. [Volume documentation](https://docs.fly.io/volumes/overview) |
| Google Cloud Run | Better as a later scaling option after an architecture change | Its writable container filesystem is in-memory and nonpersistent. Move jobs/results to a durable database, audio/models to object storage, and transcription to durable background execution with suitable CPU allocation. [Runtime contract](https://docs.cloud.google.com/run/docs/container-contract) |

Before exposing the app publicly, add authentication, HTTPS, per-user job access, and upload/job rate limits. The current app is designed for trusted personal use. Cloud-hosted speech processing happens on the server, not on the user's Mac. Also run the live caption smoke test from the exact hosting network before committing to a provider: the caption library documents blocking of cloud-provider IPs. [YouTube access limitations](https://github.com/jdepoix/youtube-transcript-api#working-around-ip-bans-requestblocked-or-ipblocked-exception)
