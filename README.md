# Intelligence Studio

![Intelligence Studio logo](frontend/public/brand/logo-mark.png)

A personal-use, caption-first YouTube transcriber for your Mac. Paste a watch, Shorts, or youtu.be URL, select a caption language, then read, copy, or download TXT/SRT. Manual captions take priority over automatic captions. If captions are unavailable, upload audio/video for local speech recognition. Intelligence Studio also provides account sign-in, optional transcript insights, and the ability to email transcript text and generated insights. Generated insights remain in page memory and are not persisted.

## Build and launch locally

Requires **Python 3.11+** and **Node.js 22.12+ with npm** on macOS or Linux. Docker is not required for this option.

From the repository root:

```sh
python3 build/run.py
```

First complete **Kinde authentication setup** below. The script creates `.venv` if needed, builds and installs the Python backend with local audio support, installs the locked frontend dependencies, builds the React frontend, and starts the app at **http://127.0.0.1:8000**. After the health check succeeds, it opens your default browser. FastAPI serves both the built frontend and API, so only one server process is needed. Keep the terminal open; **Ctrl+C** stops the app and its child process. Dependencies require internet on first installation.

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
.venv/bin/uvicorn youtube_transcriber.api:app --host 127.0.0.1 --port 8000 --no-access-log
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

Open http://127.0.0.1:8001. SQLite, cached transcripts and model files persist in the named volume. `docker compose down` stops the app and retains that volume. Kinde sign-in is required; any authenticated user can create transcripts and AI insights, with each user's data kept private. The supplied commands publish only to localhost. Complete the Kinde setup below before signing in.

### Missing a newly added feature?

After pulling or changing source code, rebuild the image:

```sh
docker compose up --build -d
```

`docker compose up -d` can reuse an existing image; it does not automatically rebuild it for source changes. Open **http://127.0.0.1:8001** (the Docker port), then reload the page.

The **AI insights & action items** panel appears **below a completed transcript**, not on the initial empty screen. Generate a transcript first, then scroll below its text to choose a provider and enter your API key.

### Emailing transcripts and insights (SMTP)

To enable email delivery from the app, configure the SMTP settings in `.env` before starting the app or rebuilding its Docker container. `SMTP_HOST` and `SMTP_FROM_ADDRESS` are required. `SMTP_PORT` defaults to `587`; `SMTP_SECURITY` defaults to `starttls` and accepts `starttls` or `ssl`. `SMTP_USERNAME` and `SMTP_PASSWORD` are optional for relays that do not require authentication. STARTTLS is mandatory in `starttls` mode; SSL mode uses an implicit TLS connection. Connections time out after 15 seconds and are not retried. Keep relay credentials private and never put them in `VITE_` variables.

For Docker, Compose forwards these settings from the repository `.env`. Rebuild and restart after changing configuration:

```sh
docker compose up --build -d
```

Use a provider-issued app password or SMTP credential when required. The email feature sends transcript text as a plain-text attachment and can include generated insights in the message body. Insight output is request-scoped and is not stored in the app database. SMTP acceptance confirms relay handoff only; it does not confirm delivery to the recipient.

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

Kinde authentication and per-user job access are implemented. Before public hosting, configure an HTTPS APP_URL and Kinde callback, and add upload/job rate limits. The single-process app is intended for a small trusted user group. Cloud-hosted speech processing happens on the server, not on the user's Mac. Also run the live caption smoke test from the exact hosting network before committing to a provider: the caption library documents blocking of cloud-provider IPs. [YouTube access limitations](https://github.com/jdepoix/youtube-transcript-api#working-around-ip-bans-requestblocked-or-ipblocked-exception)

## AI insights and action items

After generating a transcript, use the **AI insights & action items** panel below it:

1. Choose **OpenAI**, **Anthropic**, **OpenRouter**, or **OpenAI-compatible**.
2. Select a model by entering its provider-specific model ID. Defaults are supplied for the named providers; model access depends on your account.
3. For a compatible provider, enter its public HTTPS API base URL, including the version path (for example, `https://api.example.com/v1`). The app appends `/chat/completions`. The endpoint/model must support Chat Completions and JSON mode; private/local endpoints, redirects and URL credentials are not supported.
4. Enter that provider's API key in the password field and click **Generate insights**. Enter the key in the app, not in a chat or source file.

The result includes a concise summary, key insights and explicit action items. Source timestamp buttons reveal the supporting transcript segment. Owners and dates are included only when stated; otherwise the UI says “Not stated.” Empty actions are reported explicitly. **Copy insights** copies the result with timestamps. Review the AI output against the transcript; source references do not guarantee factual accuracy.

### Keys, privacy and limits

The browser sends the key to the app server in an `X-AI-API-Key` header over the same connection as the UI. The server uses it only for the selected provider request. Keys are not stored in SQLite, browser storage, environment files, URLs or app logs. The form clears the key when generation starts, when changing providers and when editing the endpoint. Generated insights stay in page memory and disappear when you leave the transcript or reload. Do not enable request-header logging in a reverse proxy; use HTTPS when serving beyond localhost.

Generation sends the **transcript text** to the provider displayed in the form and can incur charges on your account. Audio transcription remains local to the app server. Provider retention policies still apply; OpenAI Responses requests set `store: false`, which does not override other provider retention policies. The app does not automatically retry billable generation requests. A timeout or navigating away can leave provider-side work running, so check usage before retrying.

AI input is limited to 120,000 UTF-8 bytes including segment labels. Larger transcripts are rejected before sending, never silently truncated. Provider context limits can be smaller. Provider requests use a 10-second connection timeout, a 90-second read timeout, a hard 100-second whole-operation deadline (including DNS and response reading), and a 5,000-token output cap; the UI stops waiting after two minutes. Authentication, quota/rate limits, timeouts, refusals and malformed responses have separate error messages.

API: `POST /transcripts/{id}/insights`, with an `X-AI-API-Key` header and body `{ "provider": "openai", "model": "gpt-4.1-mini" }`. Custom providers use `"provider": "compatible"` and `"base_url": "https://api.example.com/v1"`. Results are returned synchronously with `Cache-Control: no-store`; they do not modify the original transcript job.

Provider references: [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Anthropic tool schemas](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools), [OpenRouter API](https://openrouter.ai/docs/api_reference/overview).


## Kinde authentication setup

The integration adapts the [Kinde Python starter kit](https://github.com/kinde-starter-kits/python-starter-kit) to this app's FastAPI/React stack. The starter uses Flask and the Kinde SDK; this app uses Authlib for Kinde's standard OIDC authorization-code flow with PKCE, plus PyJWT for access-token verification. It follows [Kinde's documented OIDC integration](https://docs.kinde.com/developer-tools/about/using-kinde-without-an-sdk/). No Kinde Management API key is needed.

1. Copy the configuration template without overwriting an existing file:

   ```bash
   cp -n .env.example .env
   chmod 600 .env
   ```

   Edit `.env` locally and fill in `KINDE_CLIENT_SECRET` from your Kinde application's keys. Your domain and client ID are already in the template. Keep the secret out of chat, Git and all `VITE_` variables. The backend loads `.env` from the working directory; the launcher uses the repository directory. Compose passes only the declared auth variables into the container.

2. In Kinde, use a **Back-end web** application for client ID `be8486f517de44d88712a1f5fa8ce694`, with authorization-code flow and client-secret authentication. If that ID belongs to an SPA application, create a Back-end web application and update the ID and secret in `.env`.

3. Add the exact URLs for each way you run the app:

   | Run mode | Allowed callback URL | Allowed logout redirect URL |
   | --- | --- | --- |
   | Native launcher | `http://127.0.0.1:8000/auth/callback` | `http://127.0.0.1:8000/` |
   | Docker Compose | `http://127.0.0.1:8001/auth/callback` | `http://127.0.0.1:8001/` |
   | Vite development | `http://127.0.0.1:5173/auth/callback` | `http://127.0.0.1:5173/` |

   Use `127.0.0.1` consistently; `localhost` is a different origin. For Vite, set `APP_URL=http://127.0.0.1:5173` before starting the backend. Vite proxies `/auth` and the API. For a custom launcher port, change `APP_URL` and register its callback/logout URLs. Docker uses `DOCKER_APP_URL`, which defaults to port 8001. For remote hosting set `APP_URL` to the public HTTPS origin (no path), and register its `/auth/callback` and `/` URLs.

4. In Kinde, [register an API](https://docs.kinde.com/developer-tools/your-apis/register-manage-apis/) with identifier **`youtube-transcriber`**, authorize this web application to use it, and keep `KINDE_AUDIENCE` set to the same identifier. The backend verifies that exact audience. The API audience is required; this app does not require custom OAuth scopes, Kinde roles, or permission claims.

5. For invite-only access on the free plan, use admin-managed accounts. In Kinde, open **Settings > Environment > Policies** and turn off **Allow self sign-up**. Then open **Users > Add user**, enter the person's name and email, select the organization, and save. Manually added users do not automatically receive an invitation email; send the app URL to each approved person yourself. This is admin pre-provisioning and a personal app link, not a native pending-invitation flow. See Kinde's guides for [adding users](https://docs.kinde.com/manage-users/add-and-edit/add-and-edit-users/), [invitation flows](https://docs.kinde.com/manage-users/add-and-edit/send-invitations-webhook/) and [suspending users](https://docs.kinde.com/manage-users/access-control/delete-or-suspend-users/). Existing accounts are not removed when self sign-up is disabled; review the user list and suspend any unapproved accounts. Keep Google sign-in enabled if you use it, then test with one approved email and one new, unapproved email.

6. Run `python3 build/run.py`, or refresh Docker with `docker compose up --build -d`, then select **Sign in with Kinde**. If setup is incomplete, the app displays a setup message and protected API calls fail closed. `/health` stays public so container health checks work. `/docs` describes the API publicly; data endpoints still require the session cookie, and mutations require the `X-CSRF-Token` from `/auth/session`.

Sessions use opaque HttpOnly, SameSite=Lax cookies, with Secure enabled for HTTPS. Verified identity stays in process memory; OAuth tokens are discarded after verification. Sessions expire at the earlier of token expiry or one hour. Restarting the app signs everyone out. Logout invalidates the local session and redirects to Kinde. Run exactly one application process; a multi-instance deployment needs shared sessions and a separate worker architecture. Suspending an account in Kinde prevents future sign-ins; this implementation does not consume Kinde logout/revocation webhooks, so an existing session remains active until logout, restart, or expiry.

Each job and cache entry belongs to its creator's verified Kinde subject. Cross-user reads, exports and AI calls return 404. **Pre-authentication transcripts remain in SQLite with no owner and cannot be accessed through the app.** Regenerate them after signing in; the migration does not assign private old data to the first user.

The launcher and container disable HTTP access logs to avoid recording OAuth callback codes. If running your own server/proxy, omit query strings and sensitive headers from logs. Keep the existing localhost binding unless intentionally deploying with HTTPS.

Validation includes offline signed-token OAuth tests, empty-permissions feature access, CSRF checks and ownership isolation. A successful live login additionally requires the client secret and dashboard setup above.
