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
- Changed production configuration to refuse startup without a configured `SECRET_KEY`, and to default session cookies to Secure when the app detects a production environment.
- Confirmed GitHub Actions passed on earlier commits. The latest commit must pass its own checks before it can be considered verified.

## Findings and release gates

### P0 — Persistent data storage and recovery not verified

The app defaults to `scholar_tracker.db` (SQLite). The Render service is on the free plan, and a persistent disk or external database has not been verified. Do not enter real student records or deploy the rebuild until a persistent database/storage plan exists and a backup-and-restore test succeeds.

### P0 — The current Render start command does not initialise the rebuild database

The rebuild calls `init_db()` when run directly or through the Flask CLI, but not when Gunicorn imports `app:app`. The current Render start command is `gunicorn --bind 0.0.0.0:$PORT app:app`. A fresh rebuild deployment could therefore start without the required tables. Resolve this with a controlled release/migration step and test it against the selected persistent database before deployment.

### P1 — Login throttling is not implemented

The login handler does not currently enforce a verified rate limit. Add and test a rate limiter backed by shared persistent storage before exposing school accounts to the public internet. Do not rely on a per-process in-memory limit for a multi-worker deployment.

### P1 — Guardian identity verification is incomplete

The administrator's creation of a parent-child link is recorded as verification, but the application does not independently verify the parent's email address or phone number. A school must verify guardian authority through an approved process before access to a child's records is granted.

### P1 — School data isolation needs broader verification

The current tests cover selected role and school boundaries, not every route and every data relationship. Before production, add systematic cross-school tests for attendance, academic results, seating plans, timetables, notifications, parent links, and all create/update/delete operations. Database relationships should enforce school consistency wherever feasible.

### P1 — Deployment configuration must be checked before release

Before deploying, confirm that Render has a stable, private `SECRET_KEY`, secure cookies enabled, debug mode off, correct database configuration, and no production secrets in Git. Run a migration and rollback rehearsal against a sanitized copy of the database.

### P2 — Important planned capabilities remain unfinished

Google sign-in, phone-number sign-in, independent parent contact verification, account recovery, profile photos, audit history for important changes, outbound SMS/email delivery, student-to-account linking, and several timetable/calendar workflows remain incomplete or require further verification.

## Required pre-release checklist

- [ ] Choose persistent storage (managed database or supported persistent disk) and document its cost/owner.
- [ ] Back up existing data and successfully test restore.
- [ ] Add and test shared-storage login throttling.
- [ ] Expand cross-school and role-boundary tests for every sensitive route.
- [ ] Verify all required environment variables without exposing their values.
- [ ] Run the latest CI checks and resolve all failures.
- [ ] Test the rebuild in staging with fictional data.
- [ ] Verify parent/guardian authorization workflow and privacy controls.
- [ ] Review migration, rollback, logging, and incident recovery steps.
- [ ] Obtain explicit approval before merging and changing the live service.

**Current status:** Development continues. A passing unit-test suite is necessary, but it does not by itself establish production readiness.
