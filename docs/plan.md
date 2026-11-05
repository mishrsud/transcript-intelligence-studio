# Caption-first transcriber

User-approved design, 2026-11-05. Target host: this Mac.

## Architecture

Python caption provider normalizes timestamped segments and metadata. The initial CLI proves retrieval from this Mac. Next, FastAPI and a SQLite-backed worker expose queued/processing/completed/failed jobs to a React + TypeScript + Vite UI. Manual captions in the exact requested language take priority over automatic captions. Speech-to-text is a later pluggable fallback.

## Execution sequence

- [x] Initialize Git and project guidance.
- [x] Milestone 1: Python package, strict URL parser, provider interface, timestamped JSON CLI, TXT/SRT exporters. Test parser, track preference, normalization, error classification and timestamp rounding offline. Run live manual/automatic/no-caption probes on this Mac and record actual outcomes before starting UI work.
- [x] Milestone 2: SQLite jobs and cache, FastAPI POST /transcripts, GET /transcripts/{id}, GET /transcripts/{id}/export; React URL/language form, polling, readable transcript, timestamp toggle, copy and downloads. Validate with fixture-backed integration tests and browser smoke.
- [x] Milestone 3: Cache expiry, worker recovery, bounded retries, timeout handling, clear missing-language/access/provider errors. Exercise failure paths.
- [x] Milestone 4: Choose audio acquisition and STT provider with the user; support uploads when URL acquisition fails. Limit duration, chunk audio, verify boundaries and delete temporary files.
- [x] Milestone 5: Containers, configuration and structured logging. Smoke-test the deployment host.

## Milestone 1 file map and checks

`src/youtube_transcriber/urls.py`: accept HTTP(S) watch, youtu.be and Shorts URLs on an explicit host allowlist; extract exactly one valid 11-character ID. Reject credentials, unusual ports, ambiguous IDs and unsupported paths.

`models.py`: immutable segment/transcript records, retrieval timestamp and source metadata; protocol for providers and typed application errors.

`provider.py`: bounded HTTP timeout; list tracks, select manual then automatic in the exact language; fetch and normalize; classify library exceptions without leaking raw provider payloads.

`exports.py`: JSON preserves segments; TXT joins text; SRT rounds total milliseconds before splitting into hours/minutes/seconds.

`cli.py`: URL plus --language and --format; stdout contains result, stderr contains structured errors, nonzero exit on failure.

`tests/`: write behavior tests first, observe failure, implement, run `.venv/bin/python -m pytest`. Live probes use the installed CLI and save only a concise outcome in documentation; fixtures are identified as synthetic unless actually captured.

## Evidence

See the dated evidence below. All five milestones have implementations; validation scope and limitations are explicit.

### Retrieval spike results (2026-11-05, this Mac)

25 deterministic tests pass. Live manual English retrieval: dQw4w9WgXcQ (61 segments), jNQXAC9IVRw (6), rfscVS0vtbw (2935). aqz-KE-bpKQ reports captions_missing; aaaaaaaaaaa reports video_unavailable. Live automatic English retrieval: kqtD5dpn9C8 (1642 segments). The main host feasibility gate passed, so the MVP can proceed.

### MVP implementation details

Use one SQLite worker thread in one application process; atomically claim queued rows, recover interrupted processing on startup, cache completed results for 24 hours, and retry temporary failures at most three times. `store.py` owns SQL, `worker.py` owns execution, and `api.py` owns HTTP validation and exports. Integration tests use a temporary database and injected provider. Frontend uses same-origin requests through Vite's development proxy; production assets are served by FastAPI. Bind localhost by default.


### MVP, reliability and audio results (2026-11-05)

- 37 deterministic tests pass, including one recorded manual-caption response excerpt, cache expiry, startup recovery, three-attempt retry behavior, wrapped HTTP 503 classification, body limits with and without Content-Length, duration limits, upload failures, and cleanup after terminal status persistence.
- TypeScript and Vite production build pass. Browser verified URL submission, completed transcript, timestamp toggle, copy confirmation, uploaded-file transcription and an actual SRT download.
- Native Mac live API smoke passed manual, automatic and missing-caption cases, plus TXT/SRT exports.
- Chosen audio acquisition: user uploads only, with local faster-whisper CPU inference. Default tiny model downloaded and tested. A generated 30.91-second recording yielded seven segments; all sentences were retained across the processing window, with an ordinary its/it's recognition error. No general word-perfect guarantee is implied. Whisper owns its internal windows and absolute offsets; application code does not concatenate overlapping chunks.
- Temporary upload directory verified empty after processing. First model download requires internet; audio inference stays local.
- Review fixes: wrapped retryable HTTP errors, arbitrary valid language codes, result persistence before deleting source audio, and pre-parser request-body limits.

### Deployment and operational limits

Docker image builds successfully on this Mac. Compose binds localhost:8001 and persists its own database and model cache. Native run binds localhost:8000. Exactly one worker/application process per database is supported; separate instances must use separate databases. No authentication or remote hosting is included. Cache lookup expires after 24 hours; old job records are retained in SQLite. Decoder/model accuracy and YouTube availability remain external limitations.

Final deployment smoke: Docker on this Mac passed manual/automatic/missing-caption cases, TXT/SRT exports and uploaded local audio transcription (12 segments with the container's decoder/model runtime). The distinctive boundary-test phrases occurred exactly once. Native and container segment grouping can differ while retaining the speech. Deployment verification is for this Mac, not another network or host.
