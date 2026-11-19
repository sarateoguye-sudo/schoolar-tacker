"""Scholar Tracker application foundation with basic authentication.

Do not use real student data until deployment security, permissions, and privacy
controls have been reviewed and tested.
"""
import hmac
import os
import secrets
import sqlite3
from functools import wraps
from pathlib import Path

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = BASE_DIR / "scholar_tracker.db"
ALLOWED_ROLES = {"administrator", "teacher", "parent", "student"}

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    DATABASE=os.environ.get("SCHOLAR_TRACKER_DB", str(DEFAULT_DATABASE)),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
)


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
    """Create initial tables if they do not exist."""
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
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
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
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


def csrf_token():
    """Return a per-session token for protecting form submissions."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_form_posts():
    if request.method == "POST":
        supplied = request.form.get("_csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not expected or not supplied or not hmac.compare_digest(supplied, expected):
            abort(400, description="The form expired or could not be verified. Reload and try again.")


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self'; form-action 'self'; frame-ancestors 'self'; base-uri 'self'")
    return response


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.get("user"):
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT id, school_id, full_name, email, role FROM users WHERE id = ? AND is_active = 1",
            (user_id,),
        ).fetchone()
        if g.user is None:
            session.clear()


@app.cli.command("init-db")
def init_db_command():
    """Initialise the local development database."""
    init_db()
    click.echo("Scholar Tracker database initialised.")


@app.cli.command("create-school")
@click.option("--name", prompt="School name")
@click.option("--county", prompt="County", default="", show_default=False)
def create_school_command(name, county):
    """Create a school record and print its new ID."""
    name = name.strip()
    if not name:
        raise click.ClickException("School name cannot be empty.")
    db = sqlite3.connect(app.config["DATABASE"])
    try:
        cursor = db.execute("INSERT INTO schools (name, county) VALUES (?, ?)", (name, county.strip()))
        db.commit()
        click.echo(f"School created with ID {cursor.lastrowid}.")
    finally:
        db.close()


@app.cli.command("create-user")
@click.option("--name", prompt="Full name")
@click.option("--email", prompt="Email")
@click.option("--role", type=click.Choice(sorted(ALLOWED_ROLES)), prompt="Role")
@click.option("--school-id", type=int, prompt="School ID (use 0 only for a platform-level account)", default=0)
@click.password_option(confirmation_prompt=True)
def create_user_command(name, email, role, school_id, password):
    """Create a user with a securely hashed password."""
    name, email = name.strip(), email.strip().lower()
    if not name or not email or "@" not in email:
        raise click.ClickException("Enter a valid name and email address.")
    if len(password) < 12:
        raise click.ClickException("Use a password with at least 12 characters.")
    db = sqlite3.connect(app.config["DATABASE"])
    try:
        if school_id:
            school = db.execute("SELECT id FROM schools WHERE id = ?", (school_id,)).fetchone()
            if school is None:
                raise click.ClickException("That school ID does not exist. Create the school first.")
        cursor = db.execute(
            "INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (?, ?, ?, ?, ?)",
            (school_id or None, name, email, role, generate_password_hash(password)),
        )
        db.commit()
        click.echo(f"User created with ID {cursor.lastrowid} and role {role}.")
    except sqlite3.IntegrityError:
        raise click.ClickException("That email address is already registered.")
    finally:
        db.close()


@app.get("/")
def index():
    """Show the landing page or signed-in user's dashboard."""
    if g.user:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, password_hash, is_active FROM users WHERE email = ? COLLATE NOCASE",
            (email,),
        ).fetchone()
        if user and user["is_active"] and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            flash("You are signed in.", "success")
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect, or the account is inactive.", "error")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("You have signed out.", "info")
    return redirect(url_for("login"))


@app.get("/dashboard")
@login_required
def dashboard():
    db = get_db()
    stats = {"schools": 0, "students": 0, "classes": 0, "events": 0}
    if g.user["role"] == "administrator" and g.user["school_id"] is not None:
        school_id = g.user["school_id"]
        stats = {
            "schools": 1,
            "students": db.execute("SELECT COUNT(*) FROM students WHERE school_id = ? AND is_active = 1", (school_id,)).fetchone()[0],
            "classes": db.execute("SELECT COUNT(*) FROM classes WHERE school_id = ?", (school_id,)).fetchone()[0],
            "events": db.execute("SELECT COUNT(*) FROM school_events WHERE school_id = ?", (school_id,)).fetchone()[0],
        }
    return render_template("dashboard.html", user=g.user, stats=stats)


@app.get("/admin")
@roles_required("administrator")
def admin_area():
    """Example administrator-only route; future admin features belong here."""
    return render_template("admin.html", user=g.user)


@app.route("/admin/school-data", methods=["GET", "POST"])
@roles_required("administrator")
def school_data():
    """Manage the signed-in administrator's own school records."""
    school_id = g.user["school_id"]
    if school_id is None:
        abort(403, description="This administrator account is not assigned to a school.")

    db = get_db()
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create_class":
            name = request.form.get("class_name", "").strip()
            stream = request.form.get("stream", "").strip()
            academic_year = request.form.get("academic_year", "").strip()
            if not name or len(name) > 80 or len(stream) > 40 or len(academic_year) > 20:
                flash("Enter a class name (1–80 characters). Stream and academic year must be within their limits.", "error")
            else:
                try:
                    db.execute(
                        "INSERT INTO classes (school_id, name, stream, academic_year) VALUES (?, ?, ?, ?)",
                        (school_id, name, stream, academic_year),
                    )
                    db.commit()
                    flash("Class and stream created.", "success")
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("That class, stream and academic year already exist.", "error")
        elif action == "create_student":
            full_name = request.form.get("student_name", "").strip()
            admission_number = request.form.get("admission_number", "").strip()
            class_id_raw = request.form.get("class_id", "").strip()
            if not full_name or len(full_name) > 120 or not admission_number or len(admission_number) > 40:
                flash("Enter a student name (up to 120 characters) and admission number (up to 40 characters).", "error")
            else:
                class_id = None
                if class_id_raw:
                    if not class_id_raw.isdigit():
                        flash("Select a valid class.", "error")
                        return redirect(url_for("school_data"))
                    class_row = db.execute(
                        "SELECT id FROM classes WHERE id = ? AND school_id = ?",
                        (int(class_id_raw), school_id),
                    ).fetchone()
                    if class_row is None:
                        flash("The selected class does not belong to your school.", "error")
                        return redirect(url_for("school_data"))
                    class_id = int(class_id_raw)
                try:
                    db.execute(
                        "INSERT INTO students (school_id, class_id, admission_number, full_name) VALUES (?, ?, ?, ?)",
                        (school_id, class_id, admission_number, full_name),
                    )
                    db.commit()
                    flash("Student record created.", "success")
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("That admission number is already used in your school.", "error")
        elif action == "create_teacher":
            full_name = request.form.get("teacher_name", "").strip()
            email = request.form.get("teacher_email", "").strip().lower()
            password = request.form.get("teacher_password", "")
            if not full_name or len(full_name) > 120 or not email or len(email) > 254 or "@" not in email:
                flash("Enter a valid teacher name and email address.", "error")
            elif len(password) < 12:
                flash("The temporary password must be at least 12 characters.", "error")
            else:
                try:
                    db.execute(
                        "INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (?, ?, ?, 'teacher', ?)",
                        (school_id, full_name, email, generate_password_hash(password)),
                    )
                    db.commit()
                    flash("Teacher account created. Share the temporary password securely and ask the teacher to change it when password-change support is available.", "success")
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("That email address is already registered.", "error")
        else:
            abort(400, description="Unknown school management action.")
        return redirect(url_for("school_data"))

    classes = db.execute(
        "SELECT id, name, stream, academic_year FROM classes WHERE school_id = ? ORDER BY name, stream",
        (school_id,),
    ).fetchall()
    students = db.execute(
        """SELECT students.id, students.full_name, students.admission_number, classes.name AS class_name,
                  classes.stream AS stream
           FROM students LEFT JOIN classes ON classes.id = students.class_id
           WHERE students.school_id = ? AND students.is_active = 1
           ORDER BY students.full_name""",
        (school_id,),
    ).fetchall()
    teachers = db.execute(
        "SELECT id, full_name, email, is_active FROM users WHERE school_id = ? AND role = 'teacher' ORDER BY full_name",
        (school_id,),
    ).fetchall()
    school = db.execute("SELECT name, county FROM schools WHERE id = ?", (school_id,)).fetchone()
    return render_template("school_data.html", user=g.user, school=school, classes=classes, students=students, teachers=teachers)


@app.get("/health")
def health():
    """Service health endpoint; does not expose database contents."""
    return {"status": "ok", "app": "Scholar Tracker"}


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
