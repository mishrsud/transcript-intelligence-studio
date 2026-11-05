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

## Console design and developer workflow update (2026-11-05)

User-requested scope: build/run/browser launcher under `build/`, README usage, a Google Cloud Console-inspired UI with dark default and a persistent light toggle, GitHub Actions build/test workflow, and hosting recommendations.

Implementation sequence:
1. Add `build/run.py`: resolve repo from script path, verify tools/port, install/build Python and React, start one localhost FastAPI process serving built frontend, wait for readiness, open browser, stop child on interruption. Document flags and prerequisites.
2. Separate `App.tsx` from the entry point; add theme tests and a persistent theme helper. Use console-style top bar, navigation rail, page heading, panel borders, blue accent and theme tokens. Keep core transcript behavior.
3. Add CI for Python tests/package build, frontend tests/production build, and Docker build/health smoke, with no live YouTube/model dependencies in automated tests.
4. Verify launcher startup/shutdown, both theme states and persistence, existing tests, builds, and Docker preview. Document practical hosting choices and single-instance storage constraints.

Update verification: 41 Python tests and 3 frontend theme tests pass. TypeScript/Vite production build and Docker rebuild pass. The launcher built the Python wheel and React assets, reached health readiness, served the app, and released its port on Ctrl+C. Tests cover default browser launch, occupied-port rejection, and immediate reuse after TCP TIME_WAIT. Browser checks passed dark default, light toggle, preference after reload, desktop/mobile layout and transcript display. The existing Docker preview at localhost:8001 was refreshed and opened. CI YAML parses and its build/test commands were exercised locally; the GitHub-hosted workflow itself awaits a push. Hosting recommendations and operational caveats are recorded in README.

## Bring-your-own-key AI insights (2026-11-05)

User scope: extract key insights and action items from completed transcripts, supporting OpenAI, Anthropic, OpenRouter and other OpenAI-compatible providers using the user's own key.

Design: a separate AI insights panel on completed transcripts, with provider/model selection, optional custom HTTPS base URL and a password key field. Generation is an explicit action with destination/cost disclosure. Keys and generated insights remain ephemeral; keys never enter SQLite, localStorage, URLs or logs. The UI clears the key after submission, clears old results when switching transcripts, and shows structured summary/insights/actions with source timestamps and copy support.

Backend: POST /transcripts/{id}/insights reads the stored transcript, validates a request-scoped key header, sends bounded transcript content to one provider request with no automatic retries, validates JSON and source references, and returns a normalized result. Long transcripts above the documented request limit are rejected without silent truncation. Distinguish authentication, quota/rate limit, timeout, refusal, unsupported endpoint/model and malformed output. Custom compatible endpoints use HTTPS, public address validation, DNS-pinned TLS connections, and no redirects to avoid forwarding credentials elsewhere.

Implementation: provider adapter + output schema and transport in independent modules, injectable fake transport for offline tests; API integration tests verify errors/key non-persistence; React component tests verify key handling, state reset and successful/failed extraction. CI remains offline. Live paid generation cannot be verified without a user-supplied provider key; no key is requested in chat or read from unrelated local credentials.

AI verification: 66 Python tests (25 AI tests) and 7 frontend tests pass, along with TypeScript/Vite and Docker builds. Offline cases cover all four adapter shapes, structured output/citation validation, empty actions, credential clearing/non-persistence, malformed responses, refusals, limits, TLS pinning, redirect rejection and timeouts. Review found and resolved an inactivity-timeout gap: provider network I/O now runs in a subprocess with a hard 100-second deadline and credentials delivered only through stdin. Native and Docker live tests with deliberately invalid keys returned the expected 401 without paid generation. Browser verified provider controls, custom URL input, cleared key after failure and a readable provider error. Docker localhost:8001 was refreshed and left running. Successful paid model generation remains unverified because no real user key was provided; no unrelated credentials were accessed.
