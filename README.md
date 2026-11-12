# Scholar Tracker

> **Smarter school management. Stronger school–home connections.**

Scholar Tracker is a school-management prototype designed to help schools organise student records, record lesson attendance, review attendance summaries, and share school dates in one place. It is being developed with the needs of schools in Kenya in mind.

**Project status:** Educational prototype in development — not yet ready for production school deployment.

## Why Scholar Tracker?

Keeping student records, attendance, lesson information, and school dates organised can take time. Scholar Tracker brings these workflows together in a simple web application, with the long-term goal of helping school administrators and teachers work more efficiently while making school information easier to communicate to families.

## Explore the features

| Feature | What it is designed to support |
| --- | --- |
| 📊 Dashboard | View student totals and today's attendance counts. |
| 🎓 Student register | Organise student records by admission number, class, and stream. |
| ✅ Lesson attendance | Record students as present, absent, or late by date and subject. |
| 📈 Attendance reports | Review attendance summaries across a selected date range. |
| 🗓️ School calendar | Record and display important school dates and events. |
| 🔔 Parent notification log | Review demo notifications associated with student absences. |

> **Please note:** Parent notifications are currently a demonstration log; live SMS, email, and push-notification delivery are not implemented.

## Built with

- **Python** — application logic
- **Flask** — web framework
- **SQLite** — local development database
- **HTML/CSS** — web interface

## Run locally

### Requirements

- Python 3.10 or newer
- pip

### Setup

1. Clone this repository and open the project folder:

   ```bash
   git clone https://github.com/sarateoguye-sudo/schoolar-tacker.git
   cd schoolar-tacker
   ```

2. (Recommended) Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   ```

   Windows PowerShell:

   ```powershell
   .venv\\Scripts\\Activate.ps1
   ```

   macOS/Linux:

   ```bash
   source .venv/bin/activate
   ```

3. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Start the application:

   ```bash
   python app.py
   ```

5. Open **http://127.0.0.1:5000** in your browser.

## Main pages

- Dashboard: `/`
- Student register: `/students`
- Lesson attendance: `/attendance`
- Attendance reports: `/reports`
- School calendar: `/calendar`
- Demo notifications: `/notifications`
- Health check: `/health`

## Security and privacy notice

Scholar Tracker is an educational prototype and **must not be used with real student or parent personal information yet**. The current version does not include authentication, role-based access control, production database configuration, or real notification delivery.

Before any real-school pilot, implement and test secure login, administrator/teacher/parent permissions, input validation, secure secret management, database backups, access logging, and appropriate data-protection safeguards. Configure a strong `SECRET_KEY` through an environment variable and review applicable Kenyan data-protection requirements. The included sample students are fictional.

## Project vision

The goal is to keep developing Scholar Tracker into a practical, accessible tool for school administration and communication. Planned improvements may include secure user roles, a parent portal, real notifications, and stronger deployment and privacy controls. These are goals, not claims that the features are already available.

## Feedback and collaboration

Suggestions, bug reports, and contributions are welcome. Please open a GitHub Issue describing the problem or improvement you would like to see.

---

**Scholar Tracker — organised records, informed families, and a better-connected school community.**
