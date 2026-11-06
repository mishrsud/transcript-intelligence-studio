# Kinde authentication and authorization

User-selected policy: any authenticated user may use transcript and AI features; transcripts remain private per user. Invite-only account access is managed in Kinde.

Adapt the linked Flask starter kit's confidential web application and environment configuration to FastAPI. Use Authlib's Starlette OIDC integration for authorization code + PKCE, state and nonce validation; verify access-token signature, issuer, API audience and expiry with PyJWT. This avoids copying the starter's token logging and SDK's process-global token helpers. No management API credentials are required.

Server-side in-memory sessions contain only verified identity after login. Browser receives an opaque HttpOnly, SameSite=Lax cookie (Secure on HTTPS); sessions expire at the earlier of token expiry or one hour, and restart signs everyone out. Logout invalidates locally and redirects to Kinde. CSRF tokens protect all mutations before multipart parsing. Configuration absence fails closed. The API audience remains required; no custom scopes, roles, or permission claims are required for app features.

Authentication is required for jobs, exports, uploads, and AI generation. SQLite ownership and caption-cache keys include verified Kinde subject. Legacy ownerless records remain inaccessible; recreate transcripts after login.

Implementation sequence:
- [x] Write failing tests for missing configuration, anonymous access, CSRF, cross-user reads/exports/AI/cache and token rejection; confirm authenticated users need no permission claims.
- [x] Add isolated auth/session modules, protect API before request bodies, migrate storage ownership.
- [x] Add React sign-in gate, identity/logout and send CSRF headers; show features to every authenticated user.
- [x] Add `.env.example`, native dotenv loading and Compose environment configuration; document dashboard setup and legacy data.
- [x] Run backend and frontend tests, production build, Docker smoke and independent review. Live login requires the client secret and Kinde dashboard configuration; report verification limits honestly.

Initial verification (2026-11-06): 83 backend tests and 10 frontend tests pass; TypeScript/Vite and Docker builds pass. Container /health and frontend return 200, /auth/session reports unconfigured, protected jobs return 503. Browser shows the setup screen. Independent code review found no critical/important issues. Live public discovery metadata was retrieved from the supplied Kinde domain. At that point successful live sign-in remained unverified pending the secret/dashboard configuration.

### Live authentication follow-up (2026-11-06)

Added callback diagnostics that record only a fixed stage, exception class and allowlisted OAuth reason; exception messages, provider payloads and credentials are excluded. An independent tester verified 84 backend tests, 10 frontend tests, the frontend production build and `git diff --check`. The running Docker service was healthy, and its `auth.py` and `sessions.py` hashes matched the workspace versions. Before the separate audience-hardening change below, the user retried Google sign-in at `http://127.0.0.1:8001` and confirmed that both sign-in and sign-out worked. This supersedes the initial live-unverified status above. The cause of the earlier callback failure was not established, so no specific fix is attributed to it.

### ID-token audience hardening (2026-11-06)

A regression test showed that Authlib 1.9.5 accepted a signed ID token whose `aud` named another client when `azp` matched this application's client ID. The callback now explicitly requires the configured client ID in a well-formed string or string-array audience after Authlib's other OIDC checks. A focused positive test confirms an audience array containing this client and matching `azp` remains accepted. The auth test module passes 20 tests. The full local suite reports 84 passed and two launcher tests unable to bind sockets under the sandbox; independent full-suite verification is pending. This hardening is independent of the earlier live callback failure.
