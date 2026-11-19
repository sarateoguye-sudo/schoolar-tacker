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
- Automated tests for authentication, role restrictions, school records, subject assignments and attendance boundaries

**Not implemented yet:** password reset for forgotten passwords, multi-factor authentication, login throttling, full school-level data isolation across every operation, parent/child verification, attendance audit history and correction approvals, repeated-subject lesson periods, edit/deactivate approval flows, complete school data isolation across every operation, audit logs, and production deployment hardening. Passing the starter tests does not mean the entire app is secure.

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
