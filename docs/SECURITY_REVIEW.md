# Scholar Tracker — Security and Deployment Review

**Review date:** 2026-11-20  
**Branch reviewed:** `scholar-tracker-rebuild`  
**Latest reviewed commit:** `d694b9693c2c4a0e0e77daf9984347fa5d637ddc`  
**Review type:** Static code/configuration review, automated tests, and staging deployment/log checks. This is not an independent penetration test.

## Decision

**NO-GO for production school records. Do not merge this rebuild into `main` or deploy it to the live Render service yet.**

The latest application and security CI runs both pass, and the latest rebuild commit is live on the separate staging service. However, production still has no verified persistent database/restore plan, still uses the old startup command, and has not had provider integrations or a complete route-by-route security review verified.

## Verified on 2026-11-20

- Application tests passed on latest commit: [GitHub Actions run #193](https://github.com/sarateoguye-sudo/schoolar-tacker/actions/runs/44724145369).
- Security checks passed on latest commit: [GitHub Actions run #81](https://github.com/sarateoguye-sudo/schoolar-tacker/actions/runs/44724145380).
- Latest staging deploy `dep-dc02h3uqo8tc73fgtoj0` completed successfully with commit `d694b9693c2c4a0e0e77daf9984347fa5d637ddc`.
- Render staging logs confirm `bash render-start.sh` ran, the database schema initialized, Gunicorn started, and Render's `HEAD /` and `GET /` checks returned HTTP 200.
- Staging uses `/tmp/scholar_tracker_staging.sqlite3`; this storage is ephemeral and is only for fictional test data.
- The live production service was not modified and remains on `main`.

## Work implemented in the rebuild

- Database-level limit of two parent/guardian links per student, with same-school, active-account, and administrator checks.
- SQLite backup/restore utility with integrity checks and tests using fictional data.
- Authentication improvements: email verification, password reset with expiring/single-use links, optional Google sign-in for existing verified accounts, Twilio SMS verification, verified-phone sign-in, duplicate verified phone prevention, and database-backed login throttling.
- Parent-child linking requires a verified contact method and server-side authorization checks.
- School-isolation regression tests cover selected attendance and academic assignments, unlinked parent access, calendar visibility, class/school boundaries, published seating plans, teacher timetables, and per-user notifications.
- Guarded startup script `render-start.sh` requires `SECRET_KEY` and `SCHOLAR_TRACKER_DB`, initializes the database, then starts Gunicorn.
- Production configuration refuses to start without a configured `SECRET_KEY` and defaults session cookies to Secure in production.

## Remaining release blockers

### P0 — Persistent production storage and restore are not verified

The live service uses SQLite on Render's free plan. No persistent disk or managed PostgreSQL database is configured. The backup utility's local tests do not prove that production data can be backed up and restored. Do not store real student records until a supported persistent storage plan is approved, configured, and verified with a successful restore test.

### P0 — Production still uses the old startup command

The live Render service still starts with:

```bash
gunicorn --bind 0.0.0.0:$PORT app:app
```

It has not been switched to `bash render-start.sh`. The staging service proves the guarded script can start with staging configuration, but production must first have a verified persistent database path and stable secret. The available Render connector does not expose a safe combined action to configure a persistent disk and change the live startup command. Production was deliberately left unchanged.

### P1 — Email, SMS and Google provider flows are not end-to-end verified

The application code expects SMTP variables (`SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, optional `SMTP_USERNAME`/`SMTP_PASSWORD`), Twilio variables (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`), and Google OAuth credentials (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`). They have not been configured and tested end-to-end. Do not paste secret values into source code, issues, or chat; configure them as private service environment variables after choosing the provider accounts.

### P1 — Security review is not yet comprehensive

Passing CI validates the checks currently written, not every route or attack scenario. Expand and review the authorization matrix for every role and every read/create/update/delete route, verify school isolation and parent-link changes, review session/CSRF/security headers and uploaded files, check dependency advisories, and test login-throttle behavior behind Render's proxy. The current test coverage is improved but is not an independent penetration test.

### P1 — Guardian authorization and privacy operations need school-level validation

Verifying an email address or phone number only proves control of that contact channel. The school must independently confirm that a person is authorized to access a student's records. Configure least-privilege access, data retention, backup access controls, and incident-response procedures before a real-school pilot.

### P2 — Some planned product capabilities remain unfinished or unverified

Profile-photo management, full audit history, reliable outbound notifications, complete timetable/calendar workflows, and several account/guardian administration flows need implementation or explicit testing against the master requirements. A page existing does not mean its workflow is complete.

## Release checklist

- [ ] Account owner approves the persistent-storage provider and any recurring cost.
- [ ] Configure production persistent storage without using `/tmp` or the ephemeral application filesystem.
- [ ] Back up the current production database and successfully restore it to a separate test target.
- [ ] Verify migrations and rollback using a sanitized copy of the production database.
- [ ] Configure and privately store a stable production `SECRET_KEY` and database path.
- [ ] Change the live startup command only after storage and restore are verified.
- [ ] Configure SMTP/Twilio/Google OAuth only for providers the school intends to use; test each flow in staging.
- [ ] Verify login throttling and client-IP handling behind Render's proxy.
- [ ] Finish route-by-route role and school-isolation review; test sensitive create/update/delete paths.
- [ ] Review privacy, guardian approval, backups, logs, retention, and incident response.
- [ ] Run latest CI and staging checks again after any configuration or code changes.
- [ ] Obtain explicit approval before merging the draft PR or changing production.

## Current status

**Latest CI: PASS. Latest staging deployment: LIVE and HTTP 200 checks observed. Production release: BLOCKED.** The remaining P0 storage and startup tasks require a storage decision and safe production configuration; they cannot be honestly marked complete by changing documentation or relying on staging's temporary database.
