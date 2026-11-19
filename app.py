"""Scholar Tracker — clean rebuild foundation.

This first milestone establishes the Flask application and SQLite schema.
Authentication and role-based permissions must be implemented before storing real
student information or deploying to a school.
"""
import os
import sqlite3
from pathlib import Path

import click
from flask import Flask, g, render_template

BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("SCHOLAR_TRACKER_DB", BASE_DIR / "scholar_tracker.db"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
app.config["DATABASE"] = str(DATABASE)


def get_db():
    """Open one SQLite connection for the current request."""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the initial database tables if they do not exist."""
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS schools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            county TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL CHECK (role IN ('administrator', 'teacher', 'parent', 'student')),
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (school_id) REFERENCES schools(id)
        );
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            stream TEXT NOT NULL DEFAULT '',
            academic_year TEXT,
            FOREIGN KEY (school_id) REFERENCES schools(id),
            UNIQUE (school_id, name, stream, academic_year)
        );
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            class_id INTEGER,
            admission_number TEXT NOT NULL,
            full_name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (school_id) REFERENCES schools(id),
            FOREIGN KEY (class_id) REFERENCES classes(id),
            UNIQUE (school_id, admission_number)
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            lesson_name TEXT NOT NULL DEFAULT 'Daily register',
            status TEXT NOT NULL CHECK (status IN ('present', 'absent', 'late', 'excused')),
            recorded_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (class_id) REFERENCES classes(id),
            FOREIGN KEY (recorded_by) REFERENCES users(id),
            UNIQUE (student_id, attendance_date, lesson_name)
        );
        CREATE TABLE IF NOT EXISTS school_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            event_date TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (school_id) REFERENCES schools(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        );
        """
    )
    db.commit()
    db.close()


@app.cli.command("init-db")
def init_db_command():
    """Initialise the local development database."""
    init_db()
    click.echo("Scholar Tracker database initialised.")


@app.get("/")
def index():
    """Show the project landing page and basic setup status."""
    db = get_db()
    stats = {
        "schools": db.execute("SELECT COUNT(*) FROM schools").fetchone()[0],
        "students": db.execute("SELECT COUNT(*) FROM students WHERE is_active = 1").fetchone()[0],
        "classes": db.execute("SELECT COUNT(*) FROM classes").fetchone()[0],
        "events": db.execute("SELECT COUNT(*) FROM school_events").fetchone()[0],
    }
    return render_template("index.html", stats=stats)


@app.get("/health")
def health():
    """Simple service health endpoint; does not expose database contents."""
    return {"status": "ok", "app": "Scholar Tracker"}


if __name__ == "__main__":
    init_db()
    # Debug is disabled. Use a production WSGI server for deployment.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
