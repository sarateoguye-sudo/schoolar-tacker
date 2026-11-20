"""Scholar Tracker application foundation with basic authentication.

Do not use real student data until deployment security, permissions, and privacy
controls have been reviewed and tested.
"""
import base64
import hashlib
import hmac
import os
import secrets
import smtplib
import sqlite3
import time
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = BASE_DIR / "scholar_tracker.db"
ALLOWED_ROLES = {"administrator", "teacher", "parent", "student"}
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LOCKOUT_SECONDS = 15 * 60

app = Flask(__name__)
IS_PRODUCTION = bool(os.environ.get("RENDER")) or os.environ.get("FLASK_ENV", "").lower() == "production"
configured_secret = os.environ.get("SECRET_KEY")
if IS_PRODUCTION and not configured_secret:
    raise RuntimeError("SECRET_KEY must be configured in production; refusing to start with a temporary session secret.")

app.config.update(
    SECRET_KEY=configured_secret or secrets.token_hex(32),
    DATABASE=os.environ.get("SCHOLAR_TRACKER_DB", str(DEFAULT_DATABASE)),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get(
        "COOKIE_SECURE", "1" if IS_PRODUCTION else "0"
    ) == "1",
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
            must_change_password INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (school_id) REFERENCES schools(id)
        );
        CREATE TABLE IF NOT EXISTS login_attempts (
            attempt_key TEXT PRIMARY KEY,
            attempts INTEGER NOT NULL,
            window_started INTEGER NOT NULL,
            locked_until INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS phone_verification_codes (
            user_id INTEGER PRIMARY KEY,
            code_hash TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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
        CREATE TABLE IF NOT EXISTS student_guardians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            parent_id INTEGER NOT NULL,
            relationship TEXT NOT NULL DEFAULT 'Parent',
            verified_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (school_id) REFERENCES schools(id),
            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (parent_id) REFERENCES users(id),
            FOREIGN KEY (verified_by) REFERENCES users(id),
            UNIQUE (student_id, parent_id)
        );
        CREATE TABLE IF NOT EXISTS teacher_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            subject_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (school_id) REFERENCES schools(id),
            FOREIGN KEY (teacher_id) REFERENCES users(id),
            FOREIGN KEY (class_id) REFERENCES classes(id),
            UNIQUE (teacher_id, class_id, subject_name)
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
                CREATE TABLE IF NOT EXISTS academic_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            subject_name TEXT NOT NULL,
            assessment_name TEXT NOT NULL,
            term TEXT NOT NULL,
            academic_year TEXT NOT NULL,
            score REAL NOT NULL CHECK (score >= 0),
            max_score REAL NOT NULL CHECK (max_score > 0),
            recorded_by INTEGER NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (school_id) REFERENCES schools(id),
            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (class_id) REFERENCES classes(id),
            FOREIGN KEY (recorded_by) REFERENCES users(id),
            UNIQUE (student_id, subject_name, assessment_name, term, academic_year)
        );
        CREATE INDEX IF NOT EXISTS idx_academic_results_student ON academic_results(school_id, student_id, academic_year, term);
        CREATE TABLE IF NOT EXISTS seating_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            rows_count INTEGER NOT NULL CHECK (rows_count BETWEEN 1 AND 12),
            columns_count INTEGER NOT NULL CHECK (columns_count BETWEEN 1 AND 12),
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (school_id) REFERENCES schools(id),
            FOREIGN KEY (class_id) REFERENCES classes(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS seating_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            row_number INTEGER NOT NULL CHECK (row_number BETWEEN 1 AND 12),
            column_number INTEGER NOT NULL CHECK (column_number BETWEEN 1 AND 12),
            FOREIGN KEY (plan_id) REFERENCES seating_plans(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(id),
            UNIQUE (plan_id, student_id),
            UNIQUE (plan_id, row_number, column_number)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            school_id INTEGER NOT NULL,
            student_id INTEGER,
            attendance_date TEXT,
            lesson_name TEXT,
            notification_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (school_id) REFERENCES schools(id),
            FOREIGN KEY (student_id) REFERENCES students(id),
            UNIQUE (user_id, student_id, attendance_date, lesson_name, notification_type)
        );
        CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read, created_at);
        CREATE TABLE IF NOT EXISTS timetable_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            assignment_id INTEGER NOT NULL,
            weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            room TEXT NOT NULL DEFAULT '',
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (school_id) REFERENCES schools(id),
            FOREIGN KEY (assignment_id) REFERENCES teacher_assignments(id),
            FOREIGN KEY (created_by) REFERENCES users(id),
            UNIQUE (assignment_id, weekday, start_time, end_time)
        );
        CREATE INDEX IF NOT EXISTS idx_timetable_school_day ON timetable_entries(school_id, weekday, start_time);
        """
    )
    # Enforce guardian relationships at the database layer as well as in the UI route.
    # This protects the two-guardian limit and school boundaries if another code path is added.
    db.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS validate_student_guardian_insert
        BEFORE INSERT ON student_guardians
        BEGIN
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM students
                WHERE id = NEW.student_id AND school_id = NEW.school_id AND is_active = 1
            ) THEN RAISE(ABORT, 'guardian_student_school_mismatch') END;
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM users
                WHERE id = NEW.parent_id AND school_id = NEW.school_id
                  AND role = 'parent' AND is_active = 1
            ) THEN RAISE(ABORT, 'guardian_parent_school_mismatch') END;
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM users
                WHERE id = NEW.verified_by AND school_id = NEW.school_id
                  AND role = 'administrator' AND is_active = 1
            ) THEN RAISE(ABORT, 'guardian_verifier_not_school_admin') END;
            SELECT CASE WHEN (
                SELECT COUNT(*) FROM student_guardians
                WHERE student_id = NEW.student_id AND school_id = NEW.school_id
            ) >= 2 THEN RAISE(ABORT, 'maximum_two_guardians') END;
        END;
        """
    )
    event_columns = {row[1] for row in db.execute("PRAGMA table_info(school_events)")}
    for column, definition in (
        ("event_type", "TEXT NOT NULL DEFAULT 'School event'"),
        ("start_time", "TEXT"),
        ("end_time", "TEXT"),
        ("audience", "TEXT NOT NULL DEFAULT 'Everyone'"),
    ):
        if column not in event_columns:
            db.execute(f"ALTER TABLE school_events ADD COLUMN {column} {definition}")
    user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
    for column, definition in (
        ("must_change_password", "INTEGER NOT NULL DEFAULT 0"),
        ("email_verified", "INTEGER NOT NULL DEFAULT 0"),
        ("phone_number", "TEXT"),
        ("phone_verified", "INTEGER NOT NULL DEFAULT 0"),
        ("password_reset_version", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if column not in user_columns:
            db.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
    db.commit()
    db.close()


def csrf_token():
    """Return a per-session token for protecting form submissions."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.globals["google_sign_in_enabled"] = bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


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
    response.headers.setdefault("X-Frame-Options", "DENY")
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
        if g.user["must_change_password"] and request.endpoint not in {"change_password", "logout"}:
            return redirect(url_for("change_password"))
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
            "SELECT id, school_id, full_name, email, role, must_change_password FROM users WHERE id = ? AND is_active = 1",
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
        # Use a keyed identifier so the throttle table does not store raw email addresses.
        # Pairing email and client address limits repeated guesses without locking the whole account.
        client_address = request.remote_addr or "unknown"
        attempt_key = hmac.new(
            str(app.config["SECRET_KEY"]).encode("utf-8"),
            f"{email}\0{client_address}".encode("utf-8"),
            "sha256",
        ).hexdigest()
        db = get_db()
        now = int(time.time())
        attempt = db.execute(
            "SELECT attempts, window_started, locked_until FROM login_attempts WHERE attempt_key = ?",
            (attempt_key,),
        ).fetchone()
        if attempt and attempt["locked_until"] > now:
            flash("Email or password is incorrect, or the account is temporarily unavailable. Try again later.", "error")
            return render_template("login.html")
        user = db.execute(
            "SELECT id, password_hash, is_active, must_change_password FROM users WHERE email = ? COLLATE NOCASE",
            (email,),
        ).fetchone()
        if user and user["is_active"] and check_password_hash(user["password_hash"], password):
            db.execute("DELETE FROM login_attempts WHERE attempt_key = ?", (attempt_key,))
            db.commit()
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            flash("You are signed in.", "success")
            if user["must_change_password"]:
                return redirect(url_for("change_password"))
            return redirect(url_for("dashboard"))

        if attempt is None or now - attempt["window_started"] >= LOGIN_WINDOW_SECONDS:
            attempts = 1
            window_started = now
        else:
            attempts = attempt["attempts"] + 1
            window_started = attempt["window_started"]
        locked_until = now + LOGIN_LOCKOUT_SECONDS if attempts >= LOGIN_MAX_ATTEMPTS else 0
        db.execute(
            """INSERT INTO login_attempts (attempt_key, attempts, window_started, locked_until)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(attempt_key) DO UPDATE SET
                 attempts = excluded.attempts,
                 window_started = excluded.window_started,
                 locked_until = excluded.locked_until""",
            (attempt_key, attempts, window_started, locked_until),
        )
        db.commit()
        flash("Email or password is incorrect, or the account is inactive.", "error")
    return render_template("login.html")


def _token_serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="scholar-tracker-account-security")


def _send_email(recipient, subject, body):
    """Send mail only when SMTP settings are configured; never log token links."""
    host = os.environ.get("SMTP_HOST")
    sender = os.environ.get("SMTP_FROM")
    if not host or not sender:
        app.logger.warning("Email delivery is not configured; account email was not sent.")
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(message)
        return True
    except (OSError, smtplib.SMTPException, ValueError):
        app.logger.exception("Account email delivery failed.")
        return False


def _send_sms_twilio(phone_number, message):
    """Send SMS through Twilio when credentials are configured."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    if not account_sid or not auth_token or not from_number:
        return False
    endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = urlencode({"To": phone_number, "From": from_number, "Body": message}).encode()
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    req = Request(endpoint, data=payload, headers={
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urlopen(req, timeout=10) as response:
            return 200 <= response.status < 300
    except OSError:
        app.logger.exception("SMS delivery failed.")
        return False


def _valid_phone_number(value):
    value = value.strip()
    return value.startswith("+") and value[1:].isdigit() and 8 <= len(value[1:]) <= 15


@app.route("/account/send-verification", methods=["GET", "POST"])
@login_required
def send_email_verification():
    """Send a short-lived email verification link to the signed-in account."""
    if request.method == "POST":
        db = get_db()
        user = db.execute("SELECT email, email_verified FROM users WHERE id = ?", (g.user["id"],)).fetchone()
        if user["email_verified"]:
            flash("Your email address is already verified.", "info")
        else:
            token = _token_serializer().dumps({"uid": g.user["id"], "purpose": "verify-email"})
            link = url_for("verify_email", token=token, _external=True, _scheme="https" if IS_PRODUCTION else None)
            sent = _send_email(user["email"], "Verify your Scholar Tracker email",
                               f"Use this link to verify your email address. It expires in 30 minutes.\n\n{link}\n\nIf you did not request this, ignore this message.")
            if sent:
                flash("Verification link sent. Check your email.", "success")
            else:
                flash("Email delivery is not configured or failed. Contact the school administrator.", "error")
        return redirect(url_for("send_email_verification"))
    user = get_db().execute("SELECT email, email_verified FROM users WHERE id = ?", (g.user["id"],)).fetchone()
    return render_template("account_verification.html", user=g.user, email_verified=user["email_verified"], phone_verified=g.user["id"] and get_db().execute("SELECT phone_verified FROM users WHERE id=?", (g.user["id"],)).fetchone()["phone_verified"])


@app.get("/account/verify-email/<token>")
def verify_email(token):
    try:
        payload = _token_serializer().loads(token, max_age=1800)
    except SignatureExpired:
        flash("That verification link has expired. Request a new one.", "error")
        return redirect(url_for("login"))
    except BadSignature:
        abort(400, description="Invalid verification link.")
    if payload.get("purpose") != "verify-email" or not isinstance(payload.get("uid"), int):
        abort(400, description="Invalid verification link.")
    db = get_db()
    db.execute("UPDATE users SET email_verified = 1 WHERE id = ? AND is_active = 1", (payload["uid"],))
    db.commit()
    if g.user and g.user["id"] == payload["uid"]:
        flash("Your email address is verified.", "success")
        return redirect(url_for("send_email_verification"))
    return render_template("account_token_result.html", title="Email verified", message="Your email address is verified. You can now sign in.")


@app.route("/account/verify-phone", methods=["GET", "POST"])
@login_required
def verify_phone():
    if g.user["role"] != "parent":
        abort(403)
    db = get_db()
    user = db.execute("SELECT phone_number, phone_verified FROM users WHERE id=?", (g.user["id"],)).fetchone()
    if request.method == "POST":
        action = request.form.get("action", "send")
        if action == "send":
            phone = request.form.get("phone_number", "").strip()
            if not _valid_phone_number(phone):
                flash("Enter a phone number in international format, such as +2547XXXXXXXX.", "error")
            elif not (os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN") and os.environ.get("TWILIO_FROM_NUMBER")):
                flash("Phone verification is not configured yet. Contact the system administrator.", "error")
            else:
                code = f"{secrets.randbelow(1_000_000):06d}"
                code_hash = hashlib.sha256(f"{app.config['SECRET_KEY']}:{g.user['id']}:{code}".encode()).hexdigest()
                sent = _send_sms_twilio(phone, f"Your Scholar Tracker verification code is {code}. It expires in 10 minutes.")
                if sent:
                    db.execute("INSERT INTO phone_verification_codes(user_id, code_hash, phone_number, expires_at, attempts) VALUES (?, ?, ?, ?, 0) ON CONFLICT(user_id) DO UPDATE SET code_hash=excluded.code_hash, phone_number=excluded.phone_number, expires_at=excluded.expires_at, attempts=0",
                               (g.user["id"], code_hash, phone, int(time.time()) + 600))
                    db.commit()
                    flash("Verification code sent by SMS.", "success")
                else:
                    flash("SMS delivery failed. Check the configured SMS service and try again.", "error")
        elif action == "confirm":
            code = request.form.get("code", "").strip()
            record = db.execute("SELECT * FROM phone_verification_codes WHERE user_id=?", (g.user["id"],)).fetchone()
            if not record or record["expires_at"] < int(time.time()) or record["attempts"] >= 5:
                db.execute("DELETE FROM phone_verification_codes WHERE user_id=?", (g.user["id"],))
                db.commit()
                flash("The code expired or too many attempts were made. Request a new code.", "error")
            else:
                expected = hashlib.sha256(f"{app.config['SECRET_KEY']}:{g.user['id']}:{code}".encode()).hexdigest()
                if not hmac.compare_digest(expected, record["code_hash"]):
                    db.execute("UPDATE phone_verification_codes SET attempts=attempts+1 WHERE user_id=?", (g.user["id"],))
                    db.commit()
                    flash("That verification code is incorrect.", "error")
                else:
                    db.execute("UPDATE users SET phone_number=?, phone_verified=1 WHERE id=?", (record["phone_number"], g.user["id"]))
                    db.execute("DELETE FROM phone_verification_codes WHERE user_id=?", (g.user["id"],))
                    db.commit()
                    flash("Your phone number is verified.", "success")
        return redirect(url_for("verify_phone"))
    return render_template("phone_verification.html", user=g.user, phone_number=user["phone_number"], phone_verified=user["phone_verified"])


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = get_db().execute("SELECT id, email, is_active, password_reset_version FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
        # Keep the response identical for known and unknown addresses.
        if user and user["is_active"]:
            token = _token_serializer().dumps({"uid": user["id"], "purpose": "reset-password", "reset_version": user["password_reset_version"]})
            link = url_for("reset_password", token=token, _external=True, _scheme="https" if IS_PRODUCTION else None)
            _send_email(user["email"], "Reset your Scholar Tracker password",
                        f"A password reset was requested for your account. The link expires in 30 minutes.\n\n{link}\n\nIf you did not request this, ignore this message.")
        flash("If an active account matches that email and email delivery is available, a reset link will be sent.", "info")
        return redirect(url_for("forgot_password"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        payload = _token_serializer().loads(token, max_age=1800)
    except SignatureExpired:
        flash("That password reset link has expired. Request another.", "error")
        return redirect(url_for("forgot_password"))
    except BadSignature:
        abort(400, description="Invalid password reset link.")
    if payload.get("purpose") != "reset-password" or not isinstance(payload.get("uid"), int):
        abort(400, description="Invalid password reset link.")
    current_user = get_db().execute("SELECT password_reset_version, is_active FROM users WHERE id=?", (payload["uid"],)).fetchone()
    if not current_user or not current_user["is_active"] or payload.get("reset_version") != current_user["password_reset_version"]:
        flash("That reset link has already been used or is no longer valid. Request a new one.", "error")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 12 or password != confirm:
            flash("Passwords must match and contain at least 12 characters.", "error")
        else:
            db = get_db()
            db.execute("UPDATE users SET password_hash=?, must_change_password=0, password_reset_version=password_reset_version+1 WHERE id=? AND is_active=1",
                       (generate_password_hash(password), payload["uid"]))
            db.execute("DELETE FROM login_attempts")
            db.commit()
            flash("Password updated. Please sign in.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html")


@app.get("/auth/google")
def google_login():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        flash("Google sign-in is not configured yet.", "error")
        return redirect(url_for("login"))
    try:
        from authlib.integrations.flask_client import OAuth
    except ImportError:
        app.logger.error("Authlib is missing; Google sign-in is unavailable.")
        abort(503)
    oauth = OAuth(app)
    oauth.register(name="google", client_id=client_id, client_secret=client_secret,
                   server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                   client_kwargs={"scope": "openid email profile"})
    return oauth.google.authorize_redirect(url_for("google_callback", _external=True, _scheme="https" if IS_PRODUCTION else None))


@app.get("/auth/google/callback")
def google_callback():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return redirect(url_for("login"))
    try:
        from authlib.integrations.flask_client import OAuth
    except ImportError:
        abort(503)
    oauth = OAuth(app)
    oauth.register(name="google", client_id=client_id, client_secret=client_secret,
                   server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                   client_kwargs={"scope": "openid email profile"})
    try:
        token = oauth.google.authorize_access_token()
        profile = token.get("userinfo") or oauth.google.userinfo()
    except Exception:
        app.logger.exception("Google sign-in failed.")
        flash("Google sign-in could not be completed.", "error")
        return redirect(url_for("login"))
    email = (profile.get("email") or "").strip().lower()
    if not email or not profile.get("email_verified"):
        flash("Google must confirm the email address before sign-in.", "error")
        return redirect(url_for("login"))
    user = get_db().execute("SELECT id, is_active FROM users WHERE email=? COLLATE NOCASE AND email_verified=1", (email,)).fetchone()
    if not user or not user["is_active"]:
        flash("No active, pre-verified Scholar Tracker account matches that Google email. Ask your school administrator.", "error")
        return redirect(url_for("login"))
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = True
    return redirect(url_for("dashboard"))


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
    teacher_assignments = []
    if g.user["role"] == "teacher" and g.user["school_id"] is not None:
        teacher_assignments = db.execute(
            """SELECT teacher_assignments.id, teacher_assignments.subject_name, classes.name AS class_name, classes.stream
               FROM teacher_assignments JOIN classes ON classes.id = teacher_assignments.class_id
               WHERE teacher_assignments.teacher_id = ? AND teacher_assignments.school_id = ?
               ORDER BY classes.name, classes.stream, teacher_assignments.subject_name""",
            (g.user["id"], g.user["school_id"]),
        ).fetchall()
    parent_children = []
    repeated_absences = []
    if g.user["role"] == "parent" and g.user["school_id"] is not None:
        parent_children = db.execute(
            """SELECT students.id, students.full_name, students.admission_number, classes.name AS class_name, classes.stream, student_guardians.relationship FROM student_guardians JOIN students ON students.id = student_guardians.student_id LEFT JOIN classes ON classes.id = students.class_id WHERE student_guardians.parent_id = ? AND student_guardians.school_id = ? ORDER BY students.full_name""",
            (g.user["id"], g.user["school_id"]),
        ).fetchall()
    if g.user["role"] == "administrator" and g.user["school_id"] is not None:
        repeated_absences = db.execute(
            """SELECT students.id, students.full_name, students.admission_number, classes.name AS class_name,
                      classes.stream, COUNT(DISTINCT attendance.attendance_date) AS absent_days
               FROM attendance JOIN students ON students.id = attendance.student_id
               LEFT JOIN classes ON classes.id = students.class_id
               WHERE students.school_id = ? AND attendance.status = 'absent'
                 AND attendance.attendance_date >= date('now', '-30 days')
               GROUP BY students.id, students.full_name, students.admission_number, classes.name, classes.stream
               HAVING COUNT(DISTINCT attendance.attendance_date) >= 3
               ORDER BY absent_days DESC, students.full_name LIMIT 20""",
            (g.user["school_id"],),
        ).fetchall()
    unread_notifications = db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
        (g.user["id"],),
    ).fetchone()[0]
    return render_template("dashboard.html", user=g.user, stats=stats, teacher_assignments=teacher_assignments, parent_children=parent_children, repeated_absences=repeated_absences, unread_notifications=unread_notifications)


@app.route("/seating-plan", methods=["GET", "POST"])
@login_required
def seating_plan():
    """Admin-managed seating plans; teachers and parents receive read-only views."""
    if g.user["school_id"] is None:
        abort(403)
    db = get_db()
    school_id = g.user["school_id"]
    role = g.user["role"]

    if request.method == "POST":
        if role != "administrator":
            abort(403)
        action = request.form.get("action", "create_plan")
        if action == "create_plan":
            title = request.form.get("title", "").strip()
            class_raw = request.form.get("class_id", "")
            try:
                class_id = int(class_raw)
                rows_count = int(request.form.get("rows_count", ""))
                columns_count = int(request.form.get("columns_count", ""))
            except (ValueError, TypeError):
                flash("Choose a class and valid row/column counts.", "error")
                return redirect(url_for("seating_plan"))
            class_row = db.execute("SELECT id FROM classes WHERE id=? AND school_id=?", (class_id, school_id)).fetchone()
            if not title or len(title) > 120 or class_row is None or not 1 <= rows_count <= 12 or not 1 <= columns_count <= 12:
                flash("Check the plan title, class, and layout size (1–12 rows and columns).", "error")
                return redirect(url_for("seating_plan"))
            cursor = db.execute(
                "INSERT INTO seating_plans (school_id, class_id, title, rows_count, columns_count, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                (school_id, class_id, title, rows_count, columns_count, g.user["id"]),
            )
            db.commit()
            flash("Seating plan created as a draft. Assign students, then publish it.", "success")
            return redirect(url_for("seating_plan", plan_id=cursor.lastrowid))
        plan_raw = request.form.get("plan_id", "")
        if not plan_raw.isdigit():
            abort(400, description="Invalid seating plan.")
        plan_id = int(plan_raw)
        plan = db.execute("SELECT * FROM seating_plans WHERE id=? AND school_id=?", (plan_id, school_id)).fetchone()
        if plan is None:
            abort(404)
        if action == "publish":
            db.execute("UPDATE seating_plans SET status='published', updated_at=CURRENT_TIMESTAMP WHERE id=? AND school_id=?", (plan_id, school_id))
            db.commit()
            flash("Seating plan published for permitted viewers.", "success")
            return redirect(url_for("seating_plan", plan_id=plan_id))
        if action == "save_seats":
            if plan["status"] == "published":
                flash("Unpublish the plan before editing its seats.", "error")
                return redirect(url_for("seating_plan", plan_id=plan_id))
            # Replace assignments atomically; empty seats are allowed.
            try:
                db.execute("BEGIN")
                db.execute("DELETE FROM seating_assignments WHERE plan_id=?", (plan_id,))
                occupied = set()
                assigned_students = set()
                for key, value in request.form.items():
                    if not key.startswith("seat_") or not value.strip():
                        continue
                    parts = key.split("_")
                    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                        raise ValueError("Invalid seat field.")
                    row_number, column_number, student_id = int(parts[1]), int(parts[2]), int(value)
                    if not (1 <= row_number <= plan["rows_count"] and 1 <= column_number <= plan["columns_count"]):
                        raise ValueError("Seat is outside the layout.")
                    student = db.execute("SELECT id FROM students WHERE id=? AND school_id=? AND class_id=? AND is_active=1", (student_id, school_id, plan["class_id"])).fetchone()
                    if student is None or student_id in assigned_students or (row_number, column_number) in occupied:
                        raise ValueError("Each student and seat may be used only once, and students must belong to this class.")
                    assigned_students.add(student_id)
                    occupied.add((row_number, column_number))
                    db.execute("INSERT INTO seating_assignments (plan_id, student_id, row_number, column_number) VALUES (?, ?, ?, ?)", (plan_id, student_id, row_number, column_number))
                db.execute("UPDATE seating_plans SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (plan_id,))
                db.commit()
            except (ValueError, sqlite3.IntegrityError):
                db.rollback()
                flash("Seats were not saved. Check for duplicate students, occupied seats, or students from another class.", "error")
                return redirect(url_for("seating_plan", plan_id=plan_id))
            flash("Seating assignments saved.", "success")
            return redirect(url_for("seating_plan", plan_id=plan_id))
        abort(400, description="Unknown seating-plan action.")

    classes = db.execute("SELECT id, name, stream, academic_year FROM classes WHERE school_id=? ORDER BY name, stream", (school_id,)).fetchall()
    plans = []
    selected_plan = None
    students = []
    assignments = {}
    if role == "administrator":
        plans = db.execute(
            """SELECT seating_plans.*, classes.name AS class_name, classes.stream
               FROM seating_plans JOIN classes ON classes.id=seating_plans.class_id
               WHERE seating_plans.school_id=? ORDER BY seating_plans.updated_at DESC, seating_plans.id DESC""",
            (school_id,),
        ).fetchall()
        plan_raw = request.args.get("plan_id", "")
        if plan_raw.isdigit():
            selected_plan = db.execute("SELECT * FROM seating_plans WHERE id=? AND school_id=?", (int(plan_raw), school_id)).fetchone()
            if selected_plan:
                students = db.execute("SELECT id, full_name, admission_number FROM students WHERE school_id=? AND class_id=? AND is_active=1 ORDER BY full_name", (school_id, selected_plan["class_id"])).fetchall()
                assignments = {(row["row_number"], row["column_number"]): row["student_id"] for row in db.execute("SELECT row_number, column_number, student_id FROM seating_assignments WHERE plan_id=?", (selected_plan["id"],)).fetchall()}
    elif role == "teacher":
        plans = db.execute(
            """SELECT DISTINCT seating_plans.*, classes.name AS class_name, classes.stream
               FROM seating_plans JOIN classes ON classes.id=seating_plans.class_id
               JOIN teacher_assignments ON teacher_assignments.class_id=classes.id AND teacher_assignments.school_id=classes.school_id
               WHERE seating_plans.school_id=? AND seating_plans.status='published'
                 AND teacher_assignments.teacher_id=? ORDER BY classes.name, classes.stream""",
            (school_id, g.user["id"]),
        ).fetchall()
    elif role in ("parent", "student"):
        if role == "parent":
            plans = db.execute(
                """SELECT DISTINCT seating_plans.*, classes.name AS class_name, classes.stream
                   FROM seating_plans JOIN classes ON classes.id=seating_plans.class_id
                   JOIN students ON students.class_id=classes.id
                   JOIN student_guardians ON student_guardians.student_id=students.id
                   WHERE seating_plans.school_id=? AND seating_plans.status='published'
                     AND student_guardians.parent_id=? AND student_guardians.school_id=?
                   ORDER BY classes.name, classes.stream""",
                (school_id, g.user["id"], school_id),
            ).fetchall()
        else:
            # Student accounts are not linked to student records yet; do not expose other students' seats.
            plans = []
    return render_template("seating_plan.html", user=g.user, classes=classes, plans=plans,
                           selected_plan=selected_plan, students=students, assignments=assignments)

@app.get("/seating-plan/<int:plan_id>")
@login_required
def view_seating_plan(plan_id):
    """Read-only seating plan view scoped to role, school and student/teacher links."""
    if g.user["school_id"] is None:
        abort(403)
    db = get_db()
    school_id = g.user["school_id"]
    plan = db.execute(
        """SELECT seating_plans.*, classes.name AS class_name, classes.stream
           FROM seating_plans JOIN classes ON classes.id=seating_plans.class_id
           WHERE seating_plans.id=? AND seating_plans.school_id=?""",
        (plan_id, school_id),
    ).fetchone()
    if plan is None:
        abort(404)
    role = g.user["role"]
    if role == "administrator":
        pass
    elif plan["status"] != "published":
        abort(404)
    elif role == "teacher":
        permitted = db.execute("SELECT 1 FROM teacher_assignments WHERE school_id=? AND class_id=? AND teacher_id=?", (school_id, plan["class_id"], g.user["id"])).fetchone()
        if permitted is None:
            abort(404)
    elif role == "parent":
        permitted = db.execute(
            """SELECT 1 FROM student_guardians JOIN students ON students.id=student_guardians.student_id
               WHERE student_guardians.parent_id=? AND student_guardians.school_id=? AND students.class_id=? LIMIT 1""",
            (g.user["id"], school_id, plan["class_id"]),
        ).fetchone()
        if permitted is None:
            abort(404)
    else:
        abort(404)
    seats = db.execute(
        """SELECT seating_assignments.row_number, seating_assignments.column_number,
                  students.id AS student_id, students.full_name, students.admission_number
           FROM seating_assignments JOIN students ON students.id=seating_assignments.student_id
           WHERE seating_assignments.plan_id=? ORDER BY seating_assignments.row_number, seating_assignments.column_number""",
        (plan_id,),
    ).fetchall()
    if role == "parent":
        # Parent sees their own child's position only; all other occupied seats remain anonymous.
        linked_ids = {row["student_id"] for row in db.execute(
            "SELECT student_id FROM student_guardians WHERE parent_id=? AND school_id=?", (g.user["id"], school_id)
        ).fetchall()}
        seats = [dict(row) if row["student_id"] in linked_ids else {
            "row_number": row["row_number"], "column_number": row["column_number"],
            "student_id": None, "full_name": "Occupied", "admission_number": ""
        } for row in seats]
    return render_template("view_seating_plan.html", user=g.user, plan=plan, seats=seats)

@app.route("/school-calendar", methods=["GET", "POST"])
@login_required
def school_calendar():
    """School-wide calendar; only administrators can publish events."""
    if g.user["school_id"] is None:
        abort(403)
    db = get_db()
    if request.method == "POST":
        if g.user["role"] != "administrator":
            abort(403)
        action = request.form.get("action", "create")
        if action in {"delete_event", "update_event"}:
            event_id_raw = request.form.get("event_id", "").strip()
            if not event_id_raw.isdigit():
                abort(400, description="Invalid calendar event.")
            event = db.execute("SELECT id FROM school_events WHERE id = ? AND school_id = ?", (int(event_id_raw), g.user["school_id"])).fetchone()
            if event is None:
                abort(404)
            if action == "delete_event":
                db.execute("DELETE FROM school_events WHERE id = ? AND school_id = ?", (int(event_id_raw), g.user["school_id"]))
                db.commit()
                flash("Calendar event deleted.", "success")
                return redirect(url_for("school_calendar"))
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            event_date = request.form.get("event_date", "").strip()
            event_type = request.form.get("event_type", "School event").strip()
            start_time = request.form.get("start_time", "").strip() or None
            end_time = request.form.get("end_time", "").strip() or None
            audience = request.form.get("audience", "Everyone").strip()
            allowed_types = {"Term date", "Exam", "Holiday", "Meeting", "Sports", "School event"}
            allowed_audiences = {"Everyone", "Staff", "Parents and students"}
            from datetime import date as _date, time as _time
            try:
                _date.fromisoformat(event_date)
                if start_time: _time.fromisoformat(start_time)
                if end_time: _time.fromisoformat(end_time)
            except ValueError:
                flash("Enter a valid event date and time.", "error")
                return redirect(url_for("school_calendar"))
            if not title or len(title) > 120 or len(description) > 1000 or event_type not in allowed_types or audience not in allowed_audiences or ((start_time is None) != (end_time is None)) or (start_time and end_time and start_time >= end_time):
                flash("Check the event title, description, type, audience and time range.", "error")
                return redirect(url_for("school_calendar"))
            db.execute("""UPDATE school_events SET title=?, description=?, event_date=?, event_type=?, start_time=?, end_time=?, audience=? WHERE id=? AND school_id=?""",
                       (title, description, event_date, event_type, start_time, end_time, audience, int(event_id_raw), g.user["school_id"]))
            db.commit()
            flash("Calendar event updated.", "success")
            return redirect(url_for("school_calendar", month=event_date[:7]))
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        event_date = request.form.get("event_date", "").strip()
        event_type = request.form.get("event_type", "School event").strip()
        start_time = request.form.get("start_time", "").strip() or None
        end_time = request.form.get("end_time", "").strip() or None
        audience = request.form.get("audience", "Everyone").strip()
        allowed_types = {"Term date", "Exam", "Holiday", "Meeting", "Sports", "School event"}
        allowed_audiences = {"Everyone", "Staff", "Parents and students"}
        try:
            from datetime import date as _date, time as _time
            _date.fromisoformat(event_date)
            if start_time:
                _time.fromisoformat(start_time)
            if end_time:
                _time.fromisoformat(end_time)
        except ValueError:
            flash("Enter a valid event date and time.", "error")
            return redirect(url_for("school_calendar"))
        if not title or len(title) > 120 or len(description) > 1000 or event_type not in allowed_types or audience not in allowed_audiences:
            flash("Check the event title, description, type and audience.", "error")
        elif (start_time is None) != (end_time is None) or (start_time and end_time and start_time >= end_time):
            flash("Choose both start and end times, and make sure the end is later.", "error")
        else:
            db.execute(
                """INSERT INTO school_events
                   (school_id, title, description, event_date, created_by, event_type, start_time, end_time, audience)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (g.user["school_id"], title, description, event_date, g.user["id"], event_type, start_time, end_time, audience),
            )
            db.commit()
            flash("School calendar event published.", "success")
            return redirect(url_for("school_calendar"))
    month = request.args.get("month", "")
    from datetime import date as _date
    try:
        month_date = _date.fromisoformat(month + "-01") if month else _date.today().replace(day=1)
    except ValueError:
        abort(400, description="Choose a valid calendar month.")
    month_start = month_date.replace(day=1).isoformat()
    if month_date.month == 12:
        next_month = month_date.replace(year=month_date.year + 1, month=1, day=1)
    else:
        next_month = month_date.replace(month=month_date.month + 1, day=1)
    audience_conditions = ["audience = 'Everyone'"]
    if g.user["role"] in ("administrator", "teacher"):
        audience_conditions.append("audience = 'Staff'")
    if g.user["role"] in ("parent", "student"):
        audience_conditions.append("audience = 'Parents and students'")
    events = db.execute(
        """SELECT id, title, description, event_date, event_type, start_time, end_time, audience
           FROM school_events WHERE school_id = ? AND event_date >= ? AND event_date < ?
             AND (""" + " OR ".join(audience_conditions) + """)
           ORDER BY event_date, COALESCE(start_time, '00:00'), title""",
        (g.user["school_id"], month_start, next_month.isoformat()),
    ).fetchall()
    return render_template("school_calendar.html", user=g.user, events=events, month=month_date.strftime("%Y-%m"), month_label=month_date.strftime("%B %Y"), previous_month=month_date.replace(day=1).replace(year=(month_date.year-1 if month_date.month==1 else month_date.year), month=(12 if month_date.month==1 else month_date.month-1)).strftime("%Y-%m"), next_month=next_month.strftime("%Y-%m"))


@app.get("/teacher/timetable")
@roles_required("teacher")
def teacher_timetable():
    """Show only the signed-in teacher's scheduled lessons."""
    if g.user["school_id"] is None:
        abort(403)
    rows = get_db().execute(
        """SELECT timetable_entries.weekday, timetable_entries.start_time, timetable_entries.end_time,
                  timetable_entries.room, teacher_assignments.subject_name, classes.name AS class_name,
                  classes.stream
           FROM timetable_entries
           JOIN teacher_assignments ON teacher_assignments.id = timetable_entries.assignment_id
           JOIN classes ON classes.id = teacher_assignments.class_id
           WHERE timetable_entries.school_id = ? AND teacher_assignments.teacher_id = ?
           ORDER BY timetable_entries.weekday, timetable_entries.start_time""",
        (g.user["school_id"], g.user["id"]),
    ).fetchall()
    return render_template("teacher_timetable.html", user=g.user, timetable=rows)


@app.route("/admin/timetable", methods=["GET", "POST"])
@roles_required("administrator")
def manage_timetable():
    """Let an administrator schedule only assignments within their own school."""
    school_id = g.user["school_id"]
    if school_id is None:
        abort(403)
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action in {"delete_period", "update_period"}:
            entry_raw = request.form.get("entry_id", "").strip()
            if not entry_raw.isdigit():
                abort(400, description="Invalid timetable period.")
            existing = db.execute("""SELECT timetable_entries.id, timetable_entries.assignment_id, timetable_entries.weekday,
                                    timetable_entries.start_time, timetable_entries.end_time, timetable_entries.room,
                                    teacher_assignments.teacher_id, teacher_assignments.class_id
                                    FROM timetable_entries JOIN teacher_assignments ON teacher_assignments.id=timetable_entries.assignment_id
                                    WHERE timetable_entries.id=? AND timetable_entries.school_id=? AND teacher_assignments.school_id=?""",
                                  (int(entry_raw), school_id, school_id)).fetchone()
            if existing is None:
                abort(404)
            if action == "delete_period":
                db.execute("DELETE FROM timetable_entries WHERE id=? AND school_id=?", (int(entry_raw), school_id))
                db.commit()
                flash("Timetable period deleted.", "success")
                return redirect(url_for("manage_timetable"))
            assignment_raw = request.form.get("assignment_id", "")
        else:
            entry_raw = ""
        assignment_raw = request.form.get("assignment_id", "")
        weekday_raw = request.form.get("weekday", "")
        start_time = request.form.get("start_time", "")
        end_time = request.form.get("end_time", "")
        room = request.form.get("room", "").strip()
        from datetime import time as _time
        try:
            assignment_id = int(assignment_raw)
            weekday = int(weekday_raw)
            start_value, end_value = _time.fromisoformat(start_time), _time.fromisoformat(end_time)
        except (ValueError, TypeError):
            flash("Choose a valid lesson, weekday and start/end times.", "error")
            return redirect(url_for("manage_timetable"))
        if weekday not in range(7) or start_value >= end_value or len(room) > 80:
            flash("Check the weekday, time range and room (maximum 80 characters).", "error")
            return redirect(url_for("manage_timetable"))
        assignment = db.execute(
            """SELECT id, teacher_id, class_id FROM teacher_assignments
               WHERE id = ? AND school_id = ?""", (assignment_id, school_id)
        ).fetchone()
        if assignment is None:
            abort(403)
        overlaps = db.execute(
            """SELECT timetable_entries.id, teacher_assignments.teacher_id, teacher_assignments.class_id
               FROM timetable_entries JOIN teacher_assignments ON teacher_assignments.id = timetable_entries.assignment_id
               WHERE timetable_entries.school_id = ? AND timetable_entries.weekday = ?
                 AND timetable_entries.start_time < ? AND timetable_entries.end_time > ?
                 AND (teacher_assignments.teacher_id = ? OR teacher_assignments.class_id = ?)
                 AND timetable_entries.id != COALESCE(?, -1)""",
            (school_id, weekday, end_time, start_time, assignment["teacher_id"], assignment["class_id"],
             int(entry_raw) if action == "update_period" and entry_raw.isdigit() else None),
        ).fetchone()
        if overlaps:
            flash("Timetable conflict: this teacher or class already has a lesson during that time.", "error")
            return redirect(url_for("manage_timetable"))
        try:
            if action == "update_period":
                db.execute("""UPDATE timetable_entries SET assignment_id=?, weekday=?, start_time=?, end_time=?, room=?
                              WHERE id=? AND school_id=?""",
                           (assignment_id, weekday, start_time, end_time, room, int(entry_raw), school_id))
                flash("Timetable period updated.", "success")
            else:
                db.execute(
                    """INSERT INTO timetable_entries
                       (school_id, assignment_id, weekday, start_time, end_time, room, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (school_id, assignment_id, weekday, start_time, end_time, room, g.user["id"]),
                )
                flash("Lesson added to the timetable.", "success")
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            flash("That exact lesson period is already on the timetable.", "error")
        return redirect(url_for("manage_timetable"))
    assignments = db.execute(
        """SELECT teacher_assignments.id, teacher_assignments.subject_name, users.full_name AS teacher_name,
                  classes.name AS class_name, classes.stream
           FROM teacher_assignments JOIN users ON users.id = teacher_assignments.teacher_id
           JOIN classes ON classes.id = teacher_assignments.class_id
           WHERE teacher_assignments.school_id = ? AND users.is_active = 1
           ORDER BY classes.name, classes.stream, users.full_name, teacher_assignments.subject_name""",
        (school_id,),
    ).fetchall()
    rows = db.execute(
        """SELECT timetable_entries.id, timetable_entries.assignment_id, timetable_entries.weekday, timetable_entries.start_time,
                  timetable_entries.end_time, timetable_entries.room, teacher_assignments.subject_name,
                  users.full_name AS teacher_name, classes.name AS class_name, classes.stream
           FROM timetable_entries JOIN teacher_assignments ON teacher_assignments.id = timetable_entries.assignment_id
           JOIN users ON users.id = teacher_assignments.teacher_id JOIN classes ON classes.id = teacher_assignments.class_id
           WHERE timetable_entries.school_id = ?
           ORDER BY timetable_entries.weekday, timetable_entries.start_time, classes.name""",
        (school_id,),
    ).fetchall()
    return render_template("manage_timetable.html", user=g.user, assignments=assignments, timetable=rows)


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
        elif action == "assign_subject":
            teacher_id_raw = request.form.get("teacher_id", "").strip()
            class_id_raw = request.form.get("class_id", "").strip()
            subject_name = request.form.get("subject_name", "").strip()
            if not teacher_id_raw.isdigit() or not class_id_raw.isdigit() or not subject_name or len(subject_name) > 100:
                flash("Choose a teacher and class, and enter a subject name of up to 100 characters.", "error")
            else:
                teacher = db.execute(
                    "SELECT id FROM users WHERE id = ? AND school_id = ? AND role = 'teacher' AND is_active = 1",
                    (int(teacher_id_raw), school_id),
                ).fetchone()
                class_row = db.execute(
                    "SELECT id FROM classes WHERE id = ? AND school_id = ?",
                    (int(class_id_raw), school_id),
                ).fetchone()
                if teacher is None or class_row is None:
                    flash("The selected teacher or class is not part of your school.", "error")
                else:
                    try:
                        db.execute(
                            "INSERT INTO teacher_assignments (school_id, teacher_id, class_id, subject_name) VALUES (?, ?, ?, ?)",
                            (school_id, int(teacher_id_raw), int(class_id_raw), subject_name),
                        )
                        db.commit()
                        flash("Subject assignment created.", "success")
                    except sqlite3.IntegrityError:
                        db.rollback()
                        flash("That teacher already has this subject assigned to this class.", "error")
        elif action == "create_parent":
            full_name = request.form.get("parent_name", "").strip()
            email = request.form.get("parent_email", "").strip().lower()
            password = request.form.get("parent_password", "")
            if not full_name or len(full_name) > 120 or not email or len(email) > 254 or "@" not in email:
                flash("Enter a valid parent name and email address.", "error")
            elif len(password) < 12:
                flash("The temporary password must be at least 12 characters.", "error")
            else:
                try:
                    db.execute("INSERT INTO users (school_id, full_name, email, role, password_hash, must_change_password) VALUES (?, ?, ?, 'parent', ?, 1)", (school_id, full_name, email, generate_password_hash(password)))
                    db.commit()
                    flash("Parent account created. The parent must change the temporary password at first sign-in.", "success")
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("That email address is already registered.", "error")
        elif action == "link_parent":
            parent_id_raw = request.form.get("parent_id", "").strip()
            student_id_raw = request.form.get("student_id", "").strip()
            relationship = request.form.get("relationship", "Parent").strip()
            if not parent_id_raw.isdigit() or not student_id_raw.isdigit() or relationship not in ("Parent", "Mother", "Father", "Guardian"):
                flash("Choose a parent, student and valid relationship.", "error")
            else:
                parent = db.execute("SELECT id FROM users WHERE id = ? AND school_id = ? AND role = 'parent' AND is_active = 1", (int(parent_id_raw), school_id)).fetchone()
                student = db.execute("SELECT id FROM students WHERE id = ? AND school_id = ? AND is_active = 1", (int(student_id_raw), school_id)).fetchone()
                if parent is None or student is None:
                    flash("The selected parent and student must both belong to your school.", "error")
                else:
                    verified_parent = db.execute(
                        "SELECT email_verified, phone_verified FROM users WHERE id = ? AND school_id = ? AND role = 'parent' AND is_active = 1",
                        (int(parent_id_raw), school_id),
                    ).fetchone()
                    if not verified_parent or not (verified_parent["email_verified"] or verified_parent["phone_verified"]):
                        flash("Verify the parent's email address or phone number before linking them to a student.", "error")
                        return redirect(url_for("school_data"))
                    guardian_count = db.execute(
                        "SELECT COUNT(*) FROM student_guardians WHERE student_id = ? AND school_id = ?",
                        (int(student_id_raw), school_id),
                    ).fetchone()[0]
                    if guardian_count >= 2:
                        flash("This student already has two linked parent or guardian accounts. Remove an existing link before adding another.", "error")
                    else:
                        try:
                            db.execute("INSERT INTO student_guardians (school_id, student_id, parent_id, relationship, verified_by) VALUES (?, ?, ?, ?, ?)", (school_id, int(student_id_raw), int(parent_id_raw), relationship, g.user["id"]))
                            db.commit()
                            flash("Parent-child link created and recorded as administrator-verified.", "success")
                        except sqlite3.IntegrityError:
                            db.rollback()
                            flash("This parent is already linked to that student.", "error")
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
                        "INSERT INTO users (school_id, full_name, email, role, password_hash, must_change_password) VALUES (?, ?, ?, 'teacher', ?, 1)",
                        (school_id, full_name, email, generate_password_hash(password)),
                    )
                    db.commit()
                    flash("Teacher account created. Share the temporary password securely; the teacher must change it at first sign-in.", "success")
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
    parents = db.execute("SELECT id, full_name, email FROM users WHERE school_id = ? AND role = 'parent' AND is_active = 1 ORDER BY full_name", (school_id,)).fetchall()
    parent_links = db.execute(
        """SELECT users.full_name AS parent_name, students.full_name AS student_name, students.admission_number, student_guardians.relationship FROM student_guardians JOIN users ON users.id = student_guardians.parent_id JOIN students ON students.id = student_guardians.student_id WHERE student_guardians.school_id = ? ORDER BY users.full_name, students.full_name""",
        (school_id,),
    ).fetchall()
    assignments = db.execute(
        """SELECT teacher_assignments.id, teacher_assignments.subject_name, users.full_name AS teacher_name,
                  classes.name AS class_name, classes.stream
           FROM teacher_assignments
           JOIN users ON users.id = teacher_assignments.teacher_id
           JOIN classes ON classes.id = teacher_assignments.class_id
           WHERE teacher_assignments.school_id = ?
           ORDER BY classes.name, classes.stream, users.full_name, teacher_assignments.subject_name""",
        (school_id,),
    ).fetchall()
    school = db.execute("SELECT name, county FROM schools WHERE id = ?", (school_id,)).fetchone()
    return render_template("school_data.html", user=g.user, school=school, classes=classes, students=students, teachers=teachers, assignments=assignments, parents=parents, parent_links=parent_links)


@app.route("/teacher/attendance/<int:assignment_id>", methods=["GET", "POST"])
@roles_required("teacher")
def teacher_attendance(assignment_id):
    """Let a teacher mark attendance only for an assigned class and subject."""
    db = get_db()
    assignment = db.execute(
        """SELECT teacher_assignments.id, teacher_assignments.school_id, teacher_assignments.teacher_id,
                  teacher_assignments.class_id, teacher_assignments.subject_name, classes.name AS class_name,
                  classes.stream
           FROM teacher_assignments
           JOIN classes ON classes.id = teacher_assignments.class_id
           WHERE teacher_assignments.id = ? AND teacher_assignments.teacher_id = ?
             AND teacher_assignments.school_id = ?""",
        (assignment_id, g.user["id"], g.user["school_id"]),
    ).fetchone()
    if assignment is None:
        abort(404)
    from datetime import date
    attendance_date = request.values.get("attendance_date", date.today().isoformat())
    try:
        date.fromisoformat(attendance_date)
    except (TypeError, ValueError):
        abort(400, description="Use a valid date in YYYY-MM-DD format.")
    if request.method == "POST":
        students = db.execute(
            "SELECT id FROM students WHERE school_id = ? AND class_id = ? AND is_active = 1",
            (g.user["school_id"], assignment["class_id"]),
        ).fetchall()
        if not students:
            flash("This class has no active students to mark.", "error")
            return redirect(url_for("teacher_attendance", assignment_id=assignment_id, attendance_date=attendance_date))
        allowed_statuses = {"present", "absent", "late", "excused"}
        records = []
        for student in students:
            status = request.form.get("status_" + str(student["id"]), "")
            if status not in allowed_statuses:
                flash("Select an attendance status for every student before submitting.", "error")
                return redirect(url_for("teacher_attendance", assignment_id=assignment_id, attendance_date=attendance_date))
            records.append((student["id"], assignment["class_id"], attendance_date,
                            assignment["subject_name"], status, g.user["id"]))
        try:
            db.executemany(
                """INSERT INTO attendance (student_id, class_id, attendance_date, lesson_name, status, recorded_by)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(student_id, attendance_date, lesson_name)
                   DO UPDATE SET status = excluded.status, recorded_by = excluded.recorded_by""",
                records,
            )
            # Notify each active, administrator-linked guardian of recorded absences.
            # A database uniqueness rule prevents duplicate alerts on repeat submissions.
            for student_id, _class_id, recorded_date, lesson_name, status, _recorder_id in records:
                student = db.execute(
                    "SELECT full_name, school_id FROM students WHERE id = ? AND school_id = ?",
                    (student_id, g.user["school_id"]),
                ).fetchone()
                if student is None:
                    continue
                guardians = db.execute(
                    """SELECT users.id FROM student_guardians
                       JOIN users ON users.id = student_guardians.parent_id
                       WHERE student_guardians.student_id = ? AND student_guardians.school_id = ?
                         AND users.role = 'parent' AND users.is_active = 1 AND users.school_id = ?""",
                    (student_id, g.user["school_id"], g.user["school_id"]),
                ).fetchall()
                for guardian in guardians:
                    if status == "absent":
                        db.execute(
                            """INSERT INTO notifications
                               (user_id, school_id, student_id, attendance_date, lesson_name,
                                notification_type, title, message)
                               VALUES (?, ?, ?, ?, ?, 'attendance_absence', 'Student marked absent', ?)
                               ON CONFLICT(user_id, student_id, attendance_date, lesson_name, notification_type)
                               DO UPDATE SET title = excluded.title, message = excluded.message,
                                             is_read = 0, created_at = CURRENT_TIMESTAMP""",
                            (guardian["id"], g.user["school_id"], student_id, recorded_date, lesson_name,
                             f"{student['full_name']} was marked absent for {lesson_name} on {recorded_date}. Contact the school if you believe this is incorrect."),
                        )
                    else:
                        db.execute(
                            """UPDATE notifications SET title = 'Attendance record updated',
                                      message = ?, is_read = 1, created_at = CURRENT_TIMESTAMP
                               WHERE user_id = ? AND student_id = ? AND attendance_date = ?
                                 AND lesson_name = ? AND notification_type = 'attendance_absence'""",
                            (f"The attendance record for {student['full_name']} on {recorded_date} ({lesson_name}) was updated to {status.title()}. This replaces an earlier absence alert.",
                             guardian["id"], student_id, recorded_date, lesson_name),
                        )
            db.commit()
            flash("Attendance saved. Linked parents have been notified of any absences.", "success")
        except sqlite3.IntegrityError:
            db.rollback()
            flash("Attendance could not be saved. Check the class records and try again.", "error")
        return redirect(url_for("teacher_attendance", assignment_id=assignment_id, attendance_date=attendance_date))
    students = db.execute(
        """SELECT students.id, students.full_name, students.admission_number, attendance.status
           FROM students LEFT JOIN attendance
             ON attendance.student_id = students.id
            AND attendance.attendance_date = ?
            AND attendance.lesson_name = ?
            AND attendance.class_id = students.class_id
           WHERE students.school_id = ? AND students.class_id = ? AND students.is_active = 1
           ORDER BY students.full_name""",
        (attendance_date, assignment["subject_name"], g.user["school_id"], assignment["class_id"]),
    ).fetchall()
    return render_template("attendance_register.html", assignment=assignment, students=students, attendance_date=attendance_date)


@app.get("/attendance/reports")
@roles_required("administrator", "teacher")
def attendance_reports():
    """Show attendance history for the signed-in user."""
    from datetime import date, timedelta
    db = get_db()
    today = date.today()
    start_date = request.args.get("start_date", (today - timedelta(days=6)).isoformat())
    end_date = request.args.get("end_date", today.isoformat())
    try:
        parsed_start, parsed_end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except (TypeError, ValueError):
        abort(400, description="Choose valid start and end dates.")
    if parsed_start > parsed_end:
        abort(400, description="The start date cannot be after the end date.")
    if (parsed_end - parsed_start).days > 366:
        abort(400, description="Choose a date range of one year or less.")
    conditions = ["attendance.attendance_date BETWEEN ? AND ?"]
    params = [start_date, end_date]
    if g.user["role"] == "administrator":
        if g.user["school_id"] is None: abort(403)
        conditions.append("students.school_id = ?")
        params.append(g.user["school_id"])
    else:
        if g.user["school_id"] is None: abort(403)
        conditions.extend(["attendance.recorded_by = ?", "attendance.class_id IN (SELECT class_id FROM teacher_assignments WHERE teacher_id = ? AND school_id = ?)", "students.school_id = ?"])
        params.extend([g.user["id"], g.user["id"], g.user["school_id"], g.user["school_id"]])
    sql = """SELECT attendance.attendance_date, attendance.lesson_name, attendance.status, students.full_name AS student_name, students.admission_number, classes.name AS class_name, classes.stream, users.full_name AS recorded_by_name FROM attendance JOIN students ON students.id = attendance.student_id JOIN classes ON classes.id = attendance.class_id LEFT JOIN users ON users.id = attendance.recorded_by WHERE """ + " AND ".join(conditions) + " ORDER BY attendance.attendance_date DESC, classes.name, students.full_name LIMIT 1000"
    records = db.execute(sql, params).fetchall()
    summary = {status: 0 for status in ("present", "absent", "late", "excused")}
    for row in records:
        if row["status"] in summary: summary[row["status"]] += 1
    return render_template("attendance_reports.html", user=g.user, records=records, summary=summary, start_date=start_date, end_date=end_date)


@app.route("/academic-reports", methods=["GET", "POST"])
@roles_required("administrator", "teacher")
def academic_reports():
    """Enter marks only for assignments within the user's permitted school/classes."""
    db = get_db()
    school_id = g.user["school_id"]
    if school_id is None:
        abort(403)
    assignments_sql = """SELECT teacher_assignments.id, teacher_assignments.class_id,
                                teacher_assignments.subject_name, classes.name AS class_name,
                                classes.stream, users.full_name AS teacher_name
                         FROM teacher_assignments
                         JOIN classes ON classes.id = teacher_assignments.class_id
                         JOIN users ON users.id = teacher_assignments.teacher_id
                         WHERE teacher_assignments.school_id = ?"""
    assignment_params = [school_id]
    if g.user["role"] == "teacher":
        assignments_sql += " AND teacher_assignments.teacher_id = ?"
        assignment_params.append(g.user["id"])
    assignments_sql += " ORDER BY classes.name, classes.stream, teacher_assignments.subject_name"
    assignments = db.execute(assignments_sql, assignment_params).fetchall()
    assignment_id_raw = request.values.get("assignment_id", "")
    assignment = None
    if assignment_id_raw:
        if not assignment_id_raw.isdigit():
            abort(400, description="Select a valid subject assignment.")
        assignment = next((row for row in assignments if row["id"] == int(assignment_id_raw)), None)
        if assignment is None:
            abort(404)
    if request.method == "POST":
        if assignment is None:
            abort(400, description="Select an assigned class and subject.")
        assessment = request.form.get("assessment_name", "").strip()
        term = request.form.get("term", "").strip()
        academic_year = request.form.get("academic_year", "").strip()
        max_score_raw = request.form.get("max_score", "").strip()
        if not assessment or len(assessment) > 100 or term not in {"Term 1", "Term 2", "Term 3"} or not academic_year.isdigit() or len(academic_year) != 4:
            flash("Enter an assessment name, a valid term, and a four-digit academic year.", "error")
            return redirect(url_for("academic_reports", assignment_id=assignment["id"]))
        try:
            max_score = float(max_score_raw)
            if not 0 < max_score <= 1000:
                raise ValueError
        except (TypeError, ValueError):
            flash("Maximum marks must be greater than 0 and no more than 1,000.", "error")
            return redirect(url_for("academic_reports", assignment_id=assignment["id"]))
        students = db.execute(
            "SELECT id FROM students WHERE school_id = ? AND class_id = ? AND is_active = 1",
            (school_id, assignment["class_id"]),
        ).fetchall()
        results = []
        for student in students:
            raw = request.form.get("score_" + str(student["id"]), "").strip()
            if raw == "":
                continue
            try:
                score = float(raw)
                if score < 0 or score > max_score:
                    raise ValueError
            except (TypeError, ValueError):
                flash("Each entered mark must be a number between zero and the maximum marks. Nothing was saved.", "error")
                return redirect(url_for("academic_reports", assignment_id=assignment["id"]))
            results.append((school_id, student["id"], assignment["class_id"], assignment["subject_name"],
                            assessment, term, academic_year, score, max_score, g.user["id"]))
        if not results:
            flash("Enter at least one student's mark before saving.", "error")
            return redirect(url_for("academic_reports", assignment_id=assignment["id"]))
        try:
            db.executemany(
                """INSERT INTO academic_results
                   (school_id, student_id, class_id, subject_name, assessment_name, term, academic_year, score, max_score, recorded_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(student_id, subject_name, assessment_name, term, academic_year)
                   DO UPDATE SET score=excluded.score, max_score=excluded.max_score,
                                 recorded_by=excluded.recorded_by, updated_at=CURRENT_TIMESTAMP""",
                results,
            )
            db.commit()
            flash(f"Saved marks for {len(results)} student(s).", "success")
        except sqlite3.IntegrityError:
            db.rollback()
            flash("Marks could not be saved. Check the student and class records.", "error")
        return redirect(url_for("academic_reports", assignment_id=assignment["id"]))
    students = []
    if assignment:
        students = db.execute(
            """SELECT id, full_name, admission_number FROM students
               WHERE school_id = ? AND class_id = ? AND is_active = 1 ORDER BY full_name""",
            (school_id, assignment["class_id"]),
        ).fetchall()
    return render_template("academic_reports.html", user=g.user, assignments=assignments,
                           assignment=assignment, students=students)


@app.get("/parent/children/<int:student_id>/reports")
@roles_required("parent")
def parent_child_reports(student_id):
    """Parents can read academic results only for a child linked to their account."""
    db = get_db()
    school_id = g.user["school_id"]
    child = db.execute(
        """SELECT students.id, students.full_name, students.admission_number
           FROM student_guardians JOIN students ON students.id = student_guardians.student_id
           WHERE student_guardians.parent_id = ? AND student_guardians.student_id = ?
             AND student_guardians.school_id = ? AND students.school_id = ? AND students.is_active = 1""",
        (g.user["id"], student_id, school_id, school_id),
    ).fetchone()
    if child is None:
        abort(404)
    records = db.execute(
        """SELECT subject_name, assessment_name, term, academic_year, score, max_score, updated_at
           FROM academic_results WHERE school_id = ? AND student_id = ?
           ORDER BY academic_year DESC, term, subject_name, assessment_name""",
        (school_id, student_id),
    ).fetchall()
    return render_template("parent_child_reports.html", user=g.user, child=child, records=records)


@app.get("/notifications")
@login_required
def notifications_inbox():
    """Show only notifications belonging to the signed-in account."""
    rows = get_db().execute(
        """SELECT id, title, message, is_read, created_at
           FROM notifications WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 100""",
        (g.user["id"],),
    ).fetchall()
    return render_template("notifications.html", user=g.user, notifications=rows)


@app.post("/notifications/<int:notification_id>/read")
@login_required
def mark_notification_read(notification_id):
    """Mark one of the signed-in user's notifications as read."""
    db = get_db()
    cursor = db.execute(
        "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
        (notification_id, g.user["id"]),
    )
    db.commit()
    if cursor.rowcount == 0:
        abort(404)
    flash("Notification marked as read.", "success")
    return redirect(url_for("notifications_inbox"))


@app.get("/parent/children/<int:student_id>/attendance")
@roles_required("parent")
def parent_child_attendance(student_id):
    """Only show attendance for a child linked to this signed-in parent."""
    db = get_db()
    link = db.execute(
        """SELECT students.id, students.full_name, students.admission_number FROM student_guardians JOIN students ON students.id = student_guardians.student_id WHERE student_guardians.parent_id = ? AND student_guardians.student_id = ? AND student_guardians.school_id = ? AND students.school_id = ? AND students.is_active = 1""",
        (g.user["id"], student_id, g.user["school_id"], g.user["school_id"]),
    ).fetchone()
    if link is None:
        abort(404)
    records = db.execute(
        """SELECT attendance.attendance_date, attendance.lesson_name, attendance.status, classes.name AS class_name, classes.stream FROM attendance JOIN classes ON classes.id = attendance.class_id WHERE attendance.student_id = ? ORDER BY attendance.attendance_date DESC LIMIT 200""",
        (student_id,),
    ).fetchall()
    return render_template("parent_child_attendance.html", user=g.user, child=link, records=records)


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Require newly created teacher accounts to replace their temporary password."""
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        row = get_db().execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (g.user["id"],),
        ).fetchone()
        if not row or not check_password_hash(row["password_hash"], current_password):
            flash("Current password is incorrect.", "error")
        elif len(new_password) < 12:
            flash("Your new password must be at least 12 characters.", "error")
        elif new_password != confirm_password:
            flash("The new passwords do not match.", "error")
        elif new_password == current_password:
            flash("Choose a new password different from the temporary password.", "error")
        else:
            get_db().execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                (generate_password_hash(new_password), g.user["id"]),
            )
            get_db().commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("dashboard"))
    return render_template("change_password.html", user=g.user)


@app.get("/health")
def health():
    """Service health endpoint; does not expose database contents."""
    return {"status": "ok", "app": "Scholar Tracker"}


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
