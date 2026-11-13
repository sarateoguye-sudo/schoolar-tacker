# Parent portal phase 2 — implementation and deployment notes

## Implemented on this feature branch

- Parent accounts are created only through emailed invitation links. Invitation tokens are random, stored as SHA-256 hashes, expire after 24 hours, and are consumed once in a transaction.
- Invitations are bound to a learner and the learner's school. The invitation email address must match the invitation record; an existing account must prove its password before another learner is linked.
- Parent sign-in uses Werkzeug password hashes, IP-based rate limits, CSRF-protected forms, secure session-cookie settings from the existing Flask configuration, and session-version checks.
- Password-reset tokens are hashed, expire after one hour, can be used once, and increment the account session version to invalidate existing sessions.
- Parent dashboard, attendance history, calendar, and notices are filtered by parent ID, school ID, and active parent-child links. Requests for unlinked or cross-school children return 404.
- Calendar and notice pages now require parent sign-in and return only the authenticated parent's school data.
- Parent privacy page shows the verified account email and linked learners, and provides password-reset and logout links.
- No offline mode, service worker, PWA caching, or offline attendance was added.

## Email delivery configuration

Invitation and password-reset links are sent only when the following environment variables are configured in the hosting provider. Never commit their values to GitHub.

- SMTP_HOST
- SMTP_PORT (defaults to 587)
- SMTP_USERNAME (optional for SMTP servers that do not require authentication)
- SMTP_PASSWORD (if SMTP authentication is required)
- SMTP_FROM

If email delivery is not configured or fails, invitation/reset tokens are invalidated and no raw token is shown in the admin page. Configure SMTP in Render before using parent accounts.

## Important remaining work before real-school use

- The current administrator account is a single global account; per-school administrator roles and school-scoped staff authorization are not implemented.
- Existing admin student/attendance screens remain single-school prototype screens. The parent portal enforces child/school scope, but the whole app is not yet a complete multi-tenant system.
- Email delivery must be configured and verified end-to-end in Render. Do not use real family/student addresses until that is done.
- Review database persistence/backups, password policy, session revocation, privacy notices/consent, parent-link correction workflow, and operational monitoring before production.
- Real SMS, push notifications, and email digests are not part of this phase.
- Only fictional test data should be used until a separate security/privacy review is complete.

## Test coverage

The tests in tests/test_parent_portal.py cover invitation expiry and single use, token hashing, CSRF rejection, parent-child access isolation, cross-school denial, school-scoped calendar/notices, and password reset/session invalidation. GitHub Actions results must be checked on the pull request before considering the work ready for review.
