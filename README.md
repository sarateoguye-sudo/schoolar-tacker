# Scholar Tracker

Scholar Tracker is a Python/Flask + SQLite school attendance management prototype. This repository is under development and has **not been deployed or published**.

## Current features

- First-run setup for a school administrator and sign-in/sign-out
- Password hashing, role checks (admin, teacher, parent), CSRF checks on POST requests, security response headers
- Admin student register, classes/streams, parent account linking and archive action
- Admin account management and teacher-to-class/subject assignments
- Lesson attendance by date, class and subject (Present, Absent, Late)
- Teacher dashboard and restrictions to assigned classes/subjects
- Parent portal limited to linked children; in-app absence alerts, unread badge, mark-as-read, and optional browser pop-up notifications while the app is open
- Admin-managed school calendar visible to parents; parents receive in-app calendar alerts
- Admin-managed weekly timetable with teacher/class/subject/time/room, teacher current-lesson panel and in-app lesson reminders
- Date-range attendance summaries and CSV export
- Basic audit log and health endpoint
- Existing prototype SQLite records are retained when the database schema is extended

## Run locally

Requires Python 3.10 or newer.

```bash
python -m venv .venv
```

Activate the environment:
- Windows PowerShell: `.venv\\Scripts\\Activate.ps1`
- macOS/Linux: `source .venv/bin/activate`

Install and run:
```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. On first run, open the setup page and create the first administrator. Choose a unique password of at least 12 characters. Administrators can then create teacher and parent accounts, link parent accounts to students, and assign teachers to classes and subjects.

Optional environment variables:
- `APP_ENV`: set to `production` on a production host. Production mode requires `SECRET_KEY`, enables secure session cookies, and refuses first-admin setup unless `SETUP_TOKEN` is configured.
- `SECRET_KEY`: required in production; set a long, random secret and keep it private.
- `SETUP_TOKEN`: required in production for first-admin setup. Use a long random token, then rotate/remove the setup route after the first admin is created.
- `SCHOLAR_DB`: optional SQLite database file path.
- `PORT`: local server port (defaults to 5000).

## Important limitations — not production ready

- This app has **not been published or deployed**. The health endpoint is informational only.
- Browser pop-up alerts require the parent to grant browser permission and keep Scholar Tracker open. Reliable background push, SMS, email, and a timetable are not implemented.
- No password-reset flow, MFA, rate limiting, formal consent workflow, database backup automation, or managed production database is included.
- Production startup requires `APP_ENV=production` and a strong `SECRET_KEY`. Production first-admin setup is blocked unless a `SETUP_TOKEN` is configured; use a long random token and do not share it. Set `APP_ENV=development` only for local development.
- The application uses SQLite and a Flask development server for local testing. Do not expose the development server directly to the public internet; use a production WSGI server and HTTPS.
- Do not use real student data until a responsible school reviews privacy, access controls, backups, hosting, and applicable Kenyan data-protection requirements.
- The UI and routes have not yet been comprehensively automated or user-tested. Verify them locally before relying on results.
- Sample students are fictional.

## Main routes

- `/` dashboard
- `/setup` first administrator setup (only while no admin exists)
- `/login`, `/logout`
- `/students` student register (admin)
- `/accounts` accounts (admin)
- `/assignments` teacher assignments (admin)
- `/attendance` lesson attendance (admin and assigned teachers)
- `/reports` attendance summaries and CSV export (admin/teacher)
- `/calendar` admin-managed school calendar visible to parents
- `/timetable` weekly timetable (admin manages; teachers and parents can view)
- `/parent` parents' portal
- `/notifications` in-app notifications and browser alert permission
- `/health` basic health check

## Suggested next steps

1. Run the application locally and fix any issues found.
2. Add automated tests for role boundaries, attendance, reports, and parent-child privacy.
3. Add reliable background push notifications only after choosing a provider, configuring credentials, HTTPS hosting, and consent.
4. Review security and privacy before any deployment.
