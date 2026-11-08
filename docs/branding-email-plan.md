# Intelligence Studio branding and account email

Approved scope: update the user-facing name to Intelligence Studio; reuse the provided brain/play artwork; send transcript text and optional generated insights through configurable SMTP; keep generated insights ephemeral.

## Architecture and ownership

- `frontend/public/brand/` contains the transparent source mark and a square favicon derived from that mark. The UI and README reference these files; no alternate logo is introduced.
- The backend email adapter owns SMTP connection setup and message delivery. It reads `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS`, and `SMTP_SECURITY`; STARTTLS is required in `starttls` mode and implicit TLS is used in `ssl` mode. The connection timeout is 15 seconds and delivery is not retried. A successful response means the SMTP relay accepted the message, not that the recipient received it.
- `.env.example` documents local configuration and Compose forwards the SMTP contract into the container. Secret values stay outside source control.
- Insight generation remains a request-scoped UI result; no database field or persistence path is added for insight output.

## Acceptance checks

1. Logo and favicon resolve from the frontend public directory; the mark retains alpha transparency and the favicon is square.
2. SMTP settings are validated and delivered with the selected TLS mode; offline tests cover configuration and expected success/failure behavior without contacting a real relay.
3. Compose resolves its environment template without exposing credential values in command output.
4. README explains transcript/insight email setup, deployment configuration, and ephemeral insight privacy.
5. Record implementation and verification evidence in `docs/plan.md`; live SMTP delivery remains unverified unless explicitly exercised with a configured test relay.

Status: implemented and deterministically verified (2026-11-08). Full evidence and the limits of live browser/SMTP validation are recorded in `docs/plan.md`.
