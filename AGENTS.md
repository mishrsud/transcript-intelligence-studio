# Project guidance

Build the personal-use YouTube transcriber caption-first. Read `docs/plan.md` before changing milestone scope; update its evidence as work progresses.

- Keep timestamped segments (text, start, duration) as the source of truth. Derive display text and exports without mutating them.
- Isolate YouTube library calls behind the caption provider interface. Keep URL parsing, selection, and exports independently testable.
- Prefer manual captions in the exact requested language, then automatic captions. Report missing languages rather than silently translating.
- Distinguish invalid input, missing captions, unavailable video, access restrictions, and temporary provider failures.
- Use deterministic tests for behavior and separate opt-in live smoke checks. Never claim live feasibility from mocked responses.
- Complete the retrieval spike on the target Mac before building the React/FastAPI UI. Record blockers honestly.
- Keep credentials, local transcripts, virtual environments, databases, and temporary audio out of Git. Delete acquired audio after processing.
- Run `python -m pytest` inside `.venv` before reporting a Python change complete.
