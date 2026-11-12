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

## Deployment preparation

A `Procfile` is included for hosts that support it. It starts the app using Gunicorn, a production WSGI server, rather than Flask's development server.

Configure these environment variables on the hosting provider:
- `APP_ENV=production`
- `SECRET_KEY`: a long, randomly generated secret; keep it private.
- `SETUP_TOKEN`: a separate long, random token needed for first-admin setup in production. Use it only for setup and remove it after the first administrator has been created.
- `SCHOLAR_DB`: path to a persistent writable data location if using SQLite.

**Do not deploy with an ephemeral filesystem for a real school:** SQLite records can be lost when the host restarts or redeploys unless the database is stored on persistent storage. Before real use, choose a hosting provider and persistent database strategy, enable HTTPS, configure backups, and complete a privacy/security review. The app has not yet been deployed.

## Environment variables

- `APP_ENV`: set to `production` on a production host. Production mode requires `SECRET_KEY` and enables secure session cookies.
- `SECRET_KEY`: required in production; set a long, random secret and keep it private.
- `SETUP_TOKEN`: required in production for first-admin setup.
- `SCHOLAR_DB`: optional SQLite database file path.
- `PORT`: local server port (defaults to 5000).

## Important limitations — not production ready

- This app has **not been published or deployed**. The health endpoint is informational only.
- Browser pop-up alerts require the parent to grant browser permission and keep Scholar Tracker open. Reliable background push, SMS, and email notifications are not included.
- No password-reset flow, MFA, rate limiting, formal consent workflow, database backup automation, or managed production database is included.
- The application uses SQLite for its prototype data. Do not expose the Flask development server directly to the public internet.
- Do not use real student data until a responsible school reviews privacy, access controls, backups, hosting, and applicable Kenyan data-protection requirements.
- The UI and routes have not yet been comprehensively automated or user-tested. Verify the screens and workflows before relying on results.
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
- `/timetable` weekly timetable
- `/parent` parents' portal
- `/notifications` in-app notifications and browser alert permission
- `/health` basic health check

## Suggested next steps

1. Choose a hosting provider and confirm whether a persistent database/storage option is available and affordable.
2. Deploy a test instance using fictional data only.
3. Test role boundaries, attendance, reports, calendar, and parent-child privacy on the hosted instance.
4. Review security and privacy before any real school deployment.
