# Scholar Tracker

**Smarter school management. Stronger school–home connections.**

Scholar Tracker is a school management project being built for schools in Kenya. Its goals include attendance, student records, school calendars, seating plans, teacher timetables, parent communication, and truancy prevention.

> **Current status:** Early prototype. Basic sign-in, password hashing, CSRF form tokens, session settings, and an administrator-only example route have been added. This is not production-ready and must not be used for real student records yet.

## Project plan

The full roadmap is in [docs/MASTER_REQUIREMENTS.md](docs/MASTER_REQUIREMENTS.md). It includes school management, parent portal, attendance, reports, calendar, notifications, dashboards, seating plans, class directors, teacher timetables, security, accessibility, and truancy prevention.

## Implemented in this milestone

- Flask app and SQLite database initialisation
- Starter database tables for schools, users, classes/streams, students, attendance, and school events
- Sign-in and sign-out routes
- Required first-sign-in password change for teacher accounts created by the school admin
- Password hashes using Werkzeug security helpers (plain-text passwords are not stored)
- CSRF token check for POST forms
- Session cookie settings and baseline response security headers
- Server-side login checks and an administrator-only example route
- CLI commands for creating a school and a user
- Administrator-only school management page for classes, streams, student register and teacher directory
- School-scoped database queries and checks that prevent assigning a student to another school's class
- Input length checks, duplicate admission-number handling and parameterized SQL for school records
- Administrator-created subject assignments linking a teacher, class/stream and subject
- Teacher dashboard that lists only the signed-in teacher's assignments
- Attendance register restricted to the teacher's own assigned class and subject
- Attendance statuses: Present, Absent, Late and Excused; all active students must receive a status before saving
- Attendance history/report page with date filters, status totals, school-scoped administrator view, and teacher-limited records
- Administrator-created parent accounts with forced temporary-password changes
- Administrator-controlled parent-to-student links, scoped to one school
- Parent dashboard lists only linked children; parent attendance view is read-only and checks the parent-child link on the server
- In-app absence alerts for linked parents when attendance is saved; repeat submissions update the same alert instead of creating duplicates
- A private notification inbox with mark-as-read controls and per-user server-side access checks
- Administrator-managed school calendar with month navigation, event types, optional times, and audience filtering
- Administrator-managed weekly teacher timetable using existing subject/class assignments; overlapping periods for the same teacher or class are rejected
- Teacher timetable view restricted to the signed-in teacher; parent and student accounts can view published school calendar events
- Administrator dashboard warning for students marked absent on at least three distinct days in the last 30 days
- Automated tests for authentication, role restrictions, school records, subject assignments, attendance boundaries and parent access boundaries

**Not implemented yet:** password reset for forgotten passwords, multi-factor authentication, independent verification documents/workflow for parent identity, attendance audit history and correction approvals, repeated-subject lesson periods, edit/deactivate approval flows, comprehensive school data isolation across every operation, full audit logs, SMS/email delivery integration, calendar/timetable editing and deletion workflows, substitute-teacher scheduling, and production deployment hardening. The parent-child link is recorded as administrator-verified, but independent email/phone verification is not implemented. GitHub Actions passed the automated tests on code commit `7f70d5a8d33259c10a95b4e730e54c6e42de638e`; login throttling and the Render startup script were added later, and their automated tests passed on commit `e23b5ea302e8375c1446fe6518afb35449ca4b23`. This is not a full security review. See [the security review and release blockers](docs/SECURITY_REVIEW.md) before considering deployment.

## Requirements

- Python 3.10 or newer
- pip

## Run locally

1. Clone the repository and switch to the rebuild branch:

   ```bash
   git clone https://github.com/sarateoguye-sudo/schoolar-tacker.git
   cd schoolar-tacker
   git switch scholar-tracker-rebuild
   ```

2. Create and activate a virtual environment.

   **Windows PowerShell**
   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

   **macOS/Linux**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Set a stable local secret key, initialise the database, and create a school. In PowerShell:

   ```powershell
   $env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
   flask --app app init-db
   flask --app app create-school
   ```

   In the create-school prompt, enter the school name and county. Keep the generated secret key private; do not commit it to GitHub. For a real deployment, use a secure secret manager and HTTPS.

5. Create the first administrator account. Use the school ID printed by the create-school command:

   ```powershell
   flask --app app create-user
   ```

   Enter the administrator's name, email, role `administrator`, school ID, and a password of at least 12 characters when prompted. The password is hashed before storage. Do not put passwords directly in command history or source files.

6. Start the local app:

   ```powershell
   flask --app app run
   ```

7. Open http://127.0.0.1:5000 and select **Sign in**. Sign in with the administrator account, then open **Manage school records** to create classes/streams, add sample students, create teacher accounts, and assign subjects to teachers. A teacher can then sign in and open the assigned attendance register.

For macOS/Linux, set the secret key with `export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"` before running the Flask commands.

## Run the automated tests

After installing dependencies, run:

```bash
python -m unittest discover -s tests -v
```

The tests use a temporary database and sample accounts; they do not need real school data.

## Database and privacy

The default database is `scholar_tracker.db`. Do not commit database files or real student records to GitHub. Use sample data only while developing.

## Render deployment gate

The rebuild is **not ready to deploy with the current live Render configuration**. It needs a verified persistent database or mounted persistent disk before any real school data is stored.

The repository includes `render-start.sh`, which initializes the schema before starting Gunicorn. If and only if persistent storage has been configured and tested, configure Render with:

- **Build command:** `pip install -r requirements.txt gunicorn`
- **Start command:** `bash render-start.sh`
- **Environment:** set a stable secret `SECRET_KEY` and set `SCHOLAR_TRACKER_DB` to the database file path on the persistent mount.

Do not point `SCHOLAR_TRACKER_DB` at the default ephemeral application filesystem for production data. Back up the existing database and test restoration before switching services. The current live service has not been switched to this branch.

## Security rules

- Never commit passwords, secret keys, API keys, private student records, or production database files.
- Do not use this prototype with real student data until authentication, authorisation, school data isolation, input validation, audit logging, backups, and privacy controls are implemented and independently tested.
- Keep debug mode off outside local development.
- Use HTTPS and an appropriate production database before public deployment.
- Check permissions on the server for every protected action. Hiding a button is not access control.
- The temporary random secret key used when `SECRET_KEY` is missing is suitable only for local experiments; set a stable secret key for local use.

## Definition of done

Track each feature as **Not Started**, **In Progress**, **Implemented**, or **Tested**. A page existing is not proof that its workflow or permissions work. Test normal use, invalid input, role boundaries, school data boundaries, and failure cases before marking a feature tested.

## Project links

- [Repository](https://github.com/sarateoguye-sudo/schoolar-tacker)
- [Rebuild branch](https://github.com/sarateoguye-sudo/schoolar-tacker/tree/scholar-tracker-rebuild)
- [Complete master requirements](docs/MASTER_REQUIREMENTS.md)


## SQLite backup and restore utility

The repository includes `scripts/backup_restore_db.py` for **local or controlled SQLite backup operations**. It verifies the database with SQLite's `quick_check`, writes backups to a new path, and refuses to overwrite existing backup or restore target files.

Examples (run from the repository root):

```bash
python scripts/backup_restore_db.py verify /path/to/scholar_tracker.db
python scripts/backup_restore_db.py backup /path/to/scholar_tracker.db /secure-backups/scholar-tracker-2026-11-20.sqlite3
python scripts/backup_restore_db.py restore /secure-backups/scholar-tracker-2026-11-20.sqlite3 /path/to/empty-restore-target.sqlite3
```

Use a private directory outside the Git repository, restrict file permissions, and encrypt backups before moving them off the machine. Never place real student records in GitHub. Test restoration into a **separate empty target path** before relying on a backup. This utility does not schedule backups, transfer them off-site, or configure Render persistent storage by itself.

## Cross-school regression tests

Run the suite with `python -m unittest discover -s tests -v`. The fictional-data isolation tests cover teacher access to another school's assignment, parent access to an unlinked child, calendar separation, and preventing an administrator from adding a student to another school's class. These tests are regression checks, not a substitute for a full independent security review.


## Account verification, sign-in and recovery configuration

The rebuild now includes email verification links, password-reset links, optional Google sign-in for existing pre-verified accounts, and parent phone verification using Twilio SMS. These flows are code-complete but **not operational until provider credentials are configured and tested**.

Configure these as private environment variables in Render (never commit them to Git):

- Email delivery: `SMTP_HOST`, `SMTP_PORT` (usually `587`), `SMTP_FROM`, and where required `SMTP_USERNAME` / `SMTP_PASSWORD`.
- Google sign-in: `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. Add the exact callback URL `https://YOUR-HOST/auth/google/callback` in Google Cloud Console. Google sign-in only matches an existing active account whose email has already been verified in Scholar Tracker; it does not create accounts automatically.
- Parent SMS verification: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER`. Configure Twilio to send SMS to the relevant countries and test delivery with a test number before use.

Parents must sign in with their temporary password, change it if required, and verify at least one contact method before the school can link them to a student. Account reset links and email-verification links expire after 30 minutes; SMS codes expire after 10 minutes and have a five-attempt limit. Provider delivery, abuse monitoring, and account recovery must be tested in staging before production.

## Staging service

A separate Render staging service is configured at https://scholar-tracker-staging.onrender.com and deploys from `scholar-tracker-rebuild`. It uses an isolated temporary SQLite path and is for fictional test data only; **it is not persistent storage and must never contain real student records**. The live service remains separate and unchanged.
