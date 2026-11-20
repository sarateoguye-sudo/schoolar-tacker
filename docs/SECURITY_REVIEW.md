# Scholar Tracker — Security and Deployment Review

**Review date:** 2026-11-20  
**Branch reviewed:** `scholar-tracker-rebuild`  
**Review type:** Static code/configuration review plus GitHub Actions results. This is not an independent penetration test.

## Decision

**NO-GO for production school records. Do not merge this rebuild into `main` or deploy it to the live Render service yet.**

The feature branch is substantially ahead of `main`. The current Render service is configured to deploy from `main`, and its configuration reports the free plan. The application defaults to a local SQLite file unless `SCHOLAR_TRACKER_DB` is set. Persistent storage for that database has not been verified. A deployment without a verified persistent database, backup and restore test risks losing school records.

## Work completed in this review

- Added a database trigger to enforce a maximum of two parent/guardian links per student, even if a future code path bypasses the administrator form.
- Added database-level checks that guardian links reference an active student and parent in the same school and are created by an active administrator of that school.
- Added a regression test for the database-level two-guardian limit.
- Added a SQLite backup/restore utility that validates backups, verifies integrity, and refuses to overwrite existing backup or restore files; added fictional-record tests for successful restore and safety failures.
- Added cross-school regression tests for teacher attendance/academic assignment access, parent access to unlinked children, calendar school separation, and student creation in another school's class.
- Added email verification links and password-reset links with 30-minute expiry; reset links are invalidated after a password reset without exposing the password hash in the token.
- Added parent SMS verification code flow with 10-minute expiry and a five-attempt limit, using Twilio only when credentials are configured.
- Added optional Google OAuth sign-in for existing active accounts with a previously verified local email; it does not auto-create accounts.
- Parent-child linking now requires a verified email address or phone number, in addition to school/role checks and the maximum-two-guardians database trigger.
- Created a separate Render staging service on the rebuild branch. It starts successfully with the guarded startup script and uses an isolated temporary SQLite path for fictional data only.
- Changed production configuration to refuse startup without a configured `SECRET_KEY`, and to default session cookies to Secure when the app detects a production environment.
- Confirmed GitHub Actions passed on earlier commits. The latest commit must pass its own checks before it can be considered verified.

## Findings and release gates

### P0 — Persistent production storage and recovery not verified

The app uses SQLite. The live Render service is on the free plan, no Render PostgreSQL database is configured, and a persistent disk has not been verified. A backup/restore utility and local fictional-data tests have been added, but no production backup has been restored and no persistent Render storage has been established. A separate staging service is live, but it deliberately uses `/tmp/scholar_tracker_staging.sqlite3`, which is ephemeral and must contain fictional data only. Do not enter real student records or deploy the rebuild until a persistent production storage plan exists and an actual backup-and-restore test succeeds.

### P0 — The current Render start command does not initialise the rebuild database

The rebuild calls `init_db()` when run directly or through the Flask CLI, but not when Gunicorn imports `app:app`. The current live Render start command is `gunicorn --bind 0.0.0.0:$PORT app:app`. I added `render-start.sh`, which fails unless `SECRET_KEY` and `SCHOLAR_TRACKER_DB` are configured, initializes the schema, then starts Gunicorn. The live Render service has not been changed to use this script; test it against the selected persistent database before deployment.

### P1 — Login throttling added, but production behavior still needs verification

The rebuild now tracks failed login attempts in the database and temporarily blocks repeated guesses for the same keyed email/client-address pair after 10 failures in a 15-minute window. A regression test has been added. Before production, verify the latest test run, confirm that the database is persistent and shared by all application workers, and confirm that the client address used behind Render's proxy is trustworthy.

### P1 — Contact verification code exists but provider setup and guardian identity review remain

The app now requires a verified email or phone contact before a parent can be linked to a student. Email verification and password recovery depend on SMTP configuration; phone verification depends on Twilio credentials; Google sign-in depends on Google OAuth credentials. None of those provider credentials has been configured or end-to-end tested in staging yet. Verifying a contact channel proves control of that email/phone, not legal guardian authority, so the school must still confirm the guardian's authority through an approved process before granting access.

### P1 — School data isolation needs broader verification

The current tests now cover selected cross-school boundaries for attendance assignments, academic assignments, unlinked parent access, calendar visibility, and student creation. They do not yet cover every role, seating plans, timetables, notifications, parent-link mutations, or every create/update/delete path. Continue expanding the matrix before production. Database relationships should enforce school consistency wherever feasible.

### P1 — Provider and deployment configuration must be checked before release

The staging service uses the rebuild branch and guarded startup script and has started successfully. SMTP, Twilio, and Google OAuth provider credentials have not been configured. The live Render service has not been changed and still runs `main` with the old startup command. Before deploying, choose and configure paid persistent storage or an appropriate managed database, configure the live start command and private secrets, test provider delivery, and rehearse migration and rollback against a sanitized copy of the database.

### P2 — Important planned capabilities remain unfinished

Google sign-in, phone-number sign-in, independent parent contact verification, account recovery, profile photos, audit history for important changes, outbound SMS/email delivery, student-to-account linking, and several timetable/calendar workflows remain incomplete or require further verification.

## Required pre-release checklist

- [ ] Choose persistent storage (managed database or supported persistent disk) and document its cost/owner.
- [ ] Back up existing data and successfully test restore. The new utility's local tests are not proof that a live Render backup can be restored.
- [ ] Verify login-throttle tests pass and that attempt records persist across restarts/workers.
- [ ] Expand cross-school and role-boundary tests for every sensitive route.
- [ ] Verify all required environment variables without exposing their values.
- [ ] Run the latest CI checks and resolve all failures.
- [ ] Test the rebuild in staging with fictional data. No staging deployment has been verified yet.
- [ ] Configure SMTP, Twilio, and Google OAuth credentials and test each configured flow in staging.
- [ ] Verify parent/guardian authorization workflow and privacy controls.
- [ ] Review migration, rollback, logging, and incident recovery steps.
- [ ] Obtain explicit approval before merging and changing the live service.

**Current status:** The staging service has been created and its initial deployment succeeded. New authentication and verification code has been added, but latest tests must pass and provider flows still need configuration and end-to-end checks. Production storage, live Render configuration, and a complete security review remain blockers. A passing unit-test suite is necessary, but it does not by itself establish production readiness.
