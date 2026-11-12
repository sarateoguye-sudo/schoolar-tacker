# Scholar Tracker resilience upgrade — implementation status

This branch deliberately removes offline/PWA caching while adding the first online-only resilience controls.

## Scope of this change
- Remove service-worker registration, offline fallback/caching, and the offline page.
- Keep the site responsive for mobile browsers; the site requires a live connection.
- Add documented acceptance criteria and security boundaries for the next implementation phases.

## Features that still require implementation
The supplied feature brief is a multi-phase product upgrade, not a safe single-file change. The following must not be treated as implemented until code and tests are merged for them:
- Parent accounts, verified invitations, child-specific portal and password recovery.
- Real SMS/email delivery and delivery receipts; no provider credentials are configured in this repository.
- Secure voice-note recording/storage and delivery.
- Risk indicators and reason-code controls.
- Unaccounted-for learners and unmarked-register queue.
- Attendance Champion workflow and scoped access.
- Weekly digest scheduler.
- Per-teacher class/stream/subject authorization.
- Append-only audit logging and multi-school data isolation.

## Required implementation order
1. Database migrations, durable database/backups, and audit foundation.
2. Teacher assignment enforcement, reason codes, one-tap present, and unmarked-register queue.
3. Parent accounts and child-link authorization, with cross-parent and cross-school denial tests.
4. Risk indicators, confidential reason access, and Attendance Champion least-privilege tasks.
5. Notification provider adapters, consent/preferences, delivery logs, and weekly digest.
6. Voice-note storage with strict authorization, file-size/type limits, retention and deletion.
7. Staged release and rollback.

## Online-only behavior
- No service worker is registered.
- No attendance or student record is cached in the browser.
- Attendance submission requires a live connection and a server response.
- Do not describe the app as working offline.

## Release gate
Do not use real student data until parent/teacher authorization, school isolation, CSRF/session protections, backups, and the full security test suite have passed. Use fictional records for development and demos.
