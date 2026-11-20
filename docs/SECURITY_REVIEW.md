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
- Changed production configuration to refuse startup without a configured `SECRET_KEY`, and to default session cookies to Secure when the app detects a production environment.
- Confirmed GitHub Actions passed on earlier commits. The latest commit must pass its own checks before it can be considered verified.

## Findings and release gates

### P0 — Persistent data storage and recovery not verified

The app defaults to `scholar_tracker.db` (SQLite). The Render service is on the free plan, no Render PostgreSQL database is configured, and a persistent disk has not been verified. A backup/restore utility and local fictional-data tests have been added, but no production backup has been restored and no persistent Render storage has been established. Do not enter real student records or deploy the rebuild until a persistent database/storage plan exists and a backup-and-restore test succeeds.

### P0 — The current Render start command does not initialise the rebuild database

The rebuild calls `init_db()` when run directly or through the Flask CLI, but not when Gunicorn imports `app:app`. The current live Render start command is `gunicorn --bind 0.0.0.0:$PORT app:app`. I added `render-start.sh`, which fails unless `SECRET_KEY` and `SCHOLAR_TRACKER_DB` are configured, initializes the schema, then starts Gunicorn. The live Render service has not been changed to use this script; test it against the selected persistent database before deployment.

### P1 — Login throttling added, but production behavior still needs verification

The rebuild now tracks failed login attempts in the database and temporarily blocks repeated guesses for the same keyed email/client-address pair after 10 failures in a 15-minute window. A regression test has been added. Before production, verify the latest test run, confirm that the database is persistent and shared by all application workers, and confirm that the client address used behind Render's proxy is trustworthy.

### P1 — Guardian identity verification is incomplete

The administrator's creation of a parent-child link is recorded as verification, but the application does not independently verify the parent's email address or phone number. A school must verify guardian authority through an approved process before access to a child's records is granted.

### P1 — School data isolation needs broader verification

The current tests now cover selected cross-school boundaries for attendance assignments, academic assignments, unlinked parent access, calendar visibility, and student creation. They do not yet cover every role, seating plans, timetables, notifications, parent-link mutations, or every create/update/delete path. Continue expanding the matrix before production. Database relationships should enforce school consistency wherever feasible.

### P1 — Deployment configuration must be checked before release

Before deploying, confirm that Render has a stable, private `SECRET_KEY`, secure cookies enabled, debug mode off, correct database configuration, and no production secrets in Git. Run a migration and rollback rehearsal against a sanitized copy of the database.

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
- [ ] Verify parent/guardian authorization workflow and privacy controls.
- [ ] Review migration, rollback, logging, and incident recovery steps.
- [ ] Obtain explicit approval before merging and changing the live service.

**Current status:** Development continues. A passing unit-test suite is necessary, but it does not by itself establish production readiness.
