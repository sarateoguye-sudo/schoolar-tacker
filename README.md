# Scholar Tracker

A beginner-friendly school attendance management prototype built with Python, Flask and SQLite.

## Features

- Dashboard with student totals and today's attendance counts
- Student register with admission number, class, stream and optional parent contact
- Lesson attendance for Present, Absent and Late, by date and subject
- Attendance summary reports by date range
- School calendar events
- Demo parent notification log for absences
- SQLite database created automatically

## Run locally

1. Install Python 3.10 or newer.
2. Open a terminal in this project folder.
3. Create and activate a virtual environment (recommended):

   ```bash
   python -m venv .venv
   ```

   Windows PowerShell: `.venv\\Scripts\\Activate.ps1`

   macOS/Linux: `source .venv/bin/activate`

4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Start the app:

   ```bash
   python app.py
   ```

6. Open http://127.0.0.1:5000 in your browser.

## Important limitations

This is an educational prototype, not ready for real school deployment. It has no login, role permissions, production database configuration, or real SMS/email delivery. The sample students are fictional. Do not enter real student or parent personal data until authentication, access controls, backups, and privacy protections are implemented. Set a strong `SECRET_KEY` environment variable before deployment. SQLite is suitable for local testing; choose and configure a managed database for a multi-user deployment.

## Main routes

- `/` dashboard
- `/students` student register
- `/attendance` lesson attendance
- `/reports` attendance summaries
- `/calendar` school events
- `/notifications` demo notification log
- `/health` basic health check
