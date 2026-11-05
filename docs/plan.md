# Caption-first transcriber

User-approved design, 2026-11-05. Target host: this Mac.

## Architecture

Python caption provider normalizes timestamped segments and metadata. The initial CLI proves retrieval from this Mac. Next, FastAPI and a SQLite-backed worker expose queued/processing/completed/failed jobs to a React + TypeScript + Vite UI. Manual captions in the exact requested language take priority over automatic captions. Speech-to-text is a later pluggable fallback.

## Execution sequence

- [x] Initialize Git and project guidance.
- [ ] Milestone 1: Python package, strict URL parser, provider interface, timestamped JSON CLI, TXT/SRT exporters. Test parser, track preference, normalization, error classification and timestamp rounding offline. Run live manual/automatic/no-caption probes on this Mac and record actual outcomes before starting UI work.
- [ ] Milestone 2: SQLite jobs and cache, FastAPI POST /transcripts, GET /transcripts/{id}, GET /transcripts/{id}/export; React URL/language form, polling, readable transcript, timestamp toggle, copy and downloads. Validate with fixture-backed integration tests and browser smoke.
- [ ] Milestone 3: Cache expiry, worker recovery, bounded retries, timeout handling, clear missing-language/access/provider errors. Exercise failure paths.
- [ ] Milestone 4: Choose audio acquisition and STT provider with the user; support uploads when URL acquisition fails. Limit duration, chunk audio, verify boundaries and delete temporary files.
- [ ] Milestone 5: Containers, configuration and structured logging. Smoke-test the deployment host.

## Milestone 1 file map and checks

`src/youtube_transcriber/urls.py`: accept HTTP(S) watch, youtu.be and Shorts URLs on an explicit host allowlist; extract exactly one valid 11-character ID. Reject credentials, unusual ports, ambiguous IDs and unsupported paths.

`models.py`: immutable segment/transcript records, retrieval timestamp and source metadata; protocol for providers and typed application errors.

`provider.py`: bounded HTTP timeout; list tracks, select manual then automatic in the exact language; fetch and normalize; classify library exceptions without leaking raw provider payloads.

`exports.py`: JSON preserves segments; TXT joins text; SRT rounds total milliseconds before splitting into hours/minutes/seconds.

`cli.py`: URL plus --language and --format; stdout contains result, stderr contains structured errors, nonzero exit on failure.

`tests/`: write behavior tests first, observe failure, implement, run `.venv/bin/python -m pytest`. Live probes use the installed CLI and save only a concise outcome in documentation; fixtures are identified as synthetic unless actually captured.

## Evidence

Pending implementation and live retrieval checks. No deployment feasibility claim yet.
