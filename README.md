# Scholar Tracker

**Smarter school management. Stronger school–home connections.**

Scholar Tracker is a school management project being built for schools in Kenya. It aims to help authorised school staff manage student records, lesson attendance, school dates, seating arrangements, teacher timetables, and parent communication.

> **Project status:** Early rebuild foundation. This version is not ready for real student data or production school deployment. Login, role permissions, parent verification, and security tests must be completed before use with real records.

## Complete project plan

The full requirements list is maintained in **[docs/MASTER_REQUIREMENTS.md](docs/MASTER_REQUIREMENTS.md)**. It covers school management, user accounts, parent portal, attendance, reports, calendar, notifications, dashboards, seating plans, class directors, teacher directory, staff timetables, security, accessibility, and truancy prevention.

## First milestone currently in the repository

- Flask application foundation
- SQLite database initialisation
- Initial tables for schools, users, classes/streams, students, attendance, and school events
- Basic project dashboard
- Health-check endpoint

These are foundation components only. The full requirements document is a roadmap; it does not mean every feature has been implemented.

## Planned development order

1. Foundation and security: authentication, roles, backend permissions, school data isolation
2. School setup: classes, streams, students and teacher directory
3. Attendance: lesson registers, corrections, audit history and reports
4. Parent portal: verified guardian links and child-specific access
5. Calendar, teacher timetables and notifications
6. Seating plans, class directors and approval workflows
7. Academic reports, attendance trends and truancy prevention
8. Security testing, backups, privacy review, accessibility and deployment

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

   **Windows**
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

4. Initialise the local database and start the app:

   ```bash
   flask --app app init-db
   flask --app app run
   ```

5. Open http://127.0.0.1:5000 in your browser.

## Database

The default local database is `scholar_tracker.db`. It is created when initialisation runs. Do not commit database files or real student records to GitHub.

## Security rules

- Never commit passwords, API keys, private student records, or production database files.
- Do not use this prototype with real student data until authentication, authorization, input validation, audit logging, and backups are implemented and tested.
- Keep Flask debug mode off outside local development.
- Use HTTPS and an appropriate production database before public deployment.
- Verify role permissions on the server for every protected operation.

## Definition of done

Track each feature as **Not Started**, **In Progress**, **Implemented**, or **Tested**. A page existing is not proof that its workflow or permissions work. Test normal use, invalid input, permission boundaries, and failure cases before marking a feature tested.

## Project links

- [Repository](https://github.com/sarateoguye-sudo/schoolar-tacker)
- [Complete master requirements](docs/MASTER_REQUIREMENTS.md)
