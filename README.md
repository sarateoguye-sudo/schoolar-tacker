# Scholar Tracker

**Smarter school management. Stronger school–home connections.**

Scholar Tracker is a school management project being built for schools in Kenya. It aims to help authorised school staff manage student records, lesson attendance, school dates, seating arrangements, and parent communication.

> **Project status:** Early rebuild foundation. This version is not ready for real student data or production school deployment. Login, role permissions, parent verification, and security tests must be completed before use with real records.

## First milestone

- Flask application foundation
- SQLite database initialisation
- Initial tables for schools, users, classes/streams, students, attendance, and school events
- Basic project dashboard
- Health-check endpoint

## Planned development order

1. Authentication, account recovery, and server-side role permissions
2. School setup, classes, streams, and student register
3. Teacher assignments and lesson attendance
4. Parent portal and verified guardian links
5. Reports and truancy insights
6. School calendar, staff timetable, and notifications
7. Seating plans and class directors
8. Security testing, backups, accessibility, and deployment

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

2. Create and activate a virtual environment:

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

The default local database is `scholar_tracker.db`. It is created in the project folder when initialisation is run. Do not commit database files or real student records to GitHub.

## Security rules

- Never commit passwords, API keys, private student records, or production database files.
- Do not use this prototype with real student data until authentication, authorisation, input validation, audit logging, and backups are implemented and tested.
- Keep Flask debug mode off outside local development.
- Use HTTPS and a managed production database before public deployment.

## Project links

- Repository: https://github.com/sarateoguye-sudo/schoolar-tacker
