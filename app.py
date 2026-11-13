import os
import re
import hmac
import secrets
import sqlite3
from datetime import date, timedelta
from functools import wraps
from flask import Flask, request, redirect, url_for, render_template_string, flash, session, abort
from markupsafe import Markup
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
# A random fallback is safe for local demos but invalidates sessions after restarts.
# Set SECRET_KEY in Render so sessions remain stable across deploys.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER") or os.environ.get("FLASK_ENV") == "production"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)
DB_PATH = os.environ.get("SCHOLAR_DB", "scholar_tracker.db")

def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token

def csrf_field():
    return Markup('<input type="hidden" name="csrf_token" value="{}">'.format(csrf_token()))

@app.before_request
def enforce_csrf():
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not supplied or not expected or not hmac.compare_digest(supplied, expected):
            abort(400, description="Invalid or missing CSRF token. Reload the page and try again.")

@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    )
    if request.is_secure or os.environ.get("RENDER"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.path not in ("/health",) and not request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response

def connect_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db

def init_db():
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_no TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            stream TEXT NOT NULL DEFAULT 'A',
            parent_contact TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id),
            lesson_date TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT 'General',
            status TEXT NOT NULL CHECK(status IN ('Present','Absent','Late')),
            marked_by TEXT NOT NULL DEFAULT 'Teacher',
            UNIQUE(student_id, lesson_date, subject)
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL,
            title TEXT NOT NULL,
            details TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            recipient TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Demo only'
        );
        CREATE TABLE IF NOT EXISTS teacher_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            teacher_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS teacher_timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            weekday TEXT NOT NULL,
            period INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            teacher_name TEXT NOT NULL,
            subject TEXT NOT NULL,
            class_name TEXT NOT NULL,
            stream TEXT NOT NULL DEFAULT 'A',
            room TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Seed clearly labelled demo lessons only when the timetable is empty.
        # These entries make the demo teacher portal testable without pretending
        # to represent a real school's timetable.
        timetable_count = db.execute("SELECT COUNT(*) FROM teacher_timetable").fetchone()[0]
        if timetable_count == 0:
            db.executemany(
                """INSERT INTO teacher_timetable
                   (weekday, period, start_time, end_time, teacher_name, subject, class_name, stream, room)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                [
                    ("Monday", 1, "09:00", "10:00", "Demo Teacher", "Computer Science", "Form 1", "A", "Computer Lab"),
                    ("Tuesday", 1, "09:00", "10:00", "Demo Teacher", "Computer Science", "Form 1", "A", "Computer Lab"),
                    ("Wednesday", 1, "09:00", "10:00", "Demo Teacher", "Computer Science", "Form 1", "A", "Computer Lab"),
                    ("Thursday", 1, "09:00", "10:00", "Demo Teacher", "Computer Science", "Form 1", "A", "Computer Lab"),
                    ("Friday", 1, "09:00", "10:00", "Demo Teacher", "Computer Science", "Form 1", "A", "Computer Lab"),
                ],
            )
        count = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        if count == 0:
            db.executemany(
                "INSERT INTO students(admission_no, full_name, class_name, stream, parent_contact) VALUES(?,?,?,?,?)",
                [
                    ("DEMO001", "Amina Sample", "Form 1", "A", ""),
                    ("DEMO002", "Brian Sample", "Form 1", "A", ""),
                    ("DEMO003", "Chao Sample", "Form 1", "B", ""),
                    ("DEMO004", "David Sample", "Form 2", "A", ""),
                ],
            )

PAGE = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="{{ url_for('static', filename='icon.svg') }}" type="image/svg+xml">
<meta name="theme-color" content="#4263eb">
<title>{{ title }} · Scholar Tracker</title>
<style>
:root{--ink:#17243b;--muted:#7b879c;--blue:#4263eb;--blue-soft:#edf1ff;--bg:#f5f7fb;--line:#e8ecf4;--white:#fff;--green:#13a879;--shadow:0 8px 30px rgba(27,45,84,.055)}
*{box-sizing:border-box}html{min-height:100%}body{margin:0;background:var(--bg);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;color:var(--ink);font-size:14px}
header{height:82px;margin-left:248px;background:rgba(255,255,255,.94);border-bottom:1px solid var(--line);padding:0 34px;display:flex;align-items:center;justify-content:space-between;gap:16px;position:sticky;top:0;z-index:5;backdrop-filter:blur(12px)}
header strong{font-size:1.02rem;letter-spacing:-.025em;color:#1c2a45}header span{font-size:.83rem;color:var(--muted)}
nav{position:fixed;left:0;top:0;bottom:0;width:248px;background:#fff;padding:25px 16px;border-right:1px solid var(--line);display:flex;flex-direction:column;gap:6px;z-index:10;overflow-y:auto}
nav:before{content:"🎓  SCHOLAR TRACKER";display:block;font-weight:850;letter-spacing:-.035em;font-size:1rem;color:#23365e;padding:5px 12px 30px}
nav:after{content:"SCHOOL WORKSPACE  ·  DEMO";font-size:.67rem;letter-spacing:.09em;font-weight:800;color:#a0aabd;padding:20px 12px 5px;order:20}
a{color:var(--blue);text-decoration:none}nav a{font-weight:650;color:#66738a;font-size:.9rem;padding:12px 13px;border-radius:11px;display:flex;align-items:center;gap:10px;transition:background .15s,color .15s}nav a:hover{background:#f0f3ff;color:var(--blue)}nav a:focus{outline:2px solid #aebeff}
main{max-width:1440px;margin:0 auto 0 248px;padding:34px 36px;min-height:calc(100vh - 140px)}.muted{color:var(--muted)}h1{font-size:clamp(1.65rem,2.5vw,2.15rem);letter-spacing:-.045em;margin:0 0 8px;font-weight:800;color:#17243b}h2{font-size:1.02rem;margin-top:0;letter-spacing:-.02em;color:#25334e}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:18px;margin:25px 0}.card,.panel{background:var(--white);border:1px solid var(--line);border-radius:17px;padding:23px;box-shadow:var(--shadow)}
.metric{font-size:2.25rem;font-weight:800;letter-spacing:-.055em;margin-top:12px;color:#1d2e50}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:18px}
form{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:15px 0}label{display:block;font-size:.8rem;font-weight:750;margin-bottom:6px;color:#52617a}input,select,textarea{padding:11px 12px;border:1px solid #dfe5ef;border-radius:10px;background:#fff;font:inherit;max-width:100%;min-height:42px;color:var(--ink)}input:focus,select:focus,textarea:focus{outline:3px solid #e4eaff;border-color:var(--blue)}.field{display:flex;flex-direction:column;gap:4px}
button,.btn{background:var(--blue);color:white;border:0;border-radius:10px;padding:11px 16px;font:inherit;font-weight:750;cursor:pointer;display:inline-block;box-shadow:0 5px 12px #4263eb25;transition:transform .15s,filter .15s}button:hover,.btn:hover{filter:brightness(.96);transform:translateY(-1px)}
table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:14px 13px;border-bottom:1px solid var(--line);font-size:.88rem}th{color:#7b879c;font-size:.75rem;background:#f8f9fc;white-space:nowrap;font-weight:800;text-transform:uppercase;letter-spacing:.04em}tr:last-child td{border-bottom:0}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:13px;margin-top:15px;background:#fff}.notice{padding:14px 16px;background:#eef3ff;border:1px solid #dce5ff;border-radius:12px;margin:16px 0;color:#3b5596;line-height:1.55}.flash{padding:13px 15px;background:#e7f8f1;color:#087951;border:1px solid #c9efdf;border-radius:11px;margin:10px 0}.pill{padding:5px 9px;border-radius:20px;background:#eef1ff;color:#405bd0;font-size:.77rem;font-weight:750}
footer{margin-left:248px;text-align:left;color:#97a1b2;padding:20px 36px;border-top:1px solid var(--line);font-size:.78rem;background:#fff}
@media(max-width:850px){header{margin-left:0;height:auto;min-height:72px;padding:18px 20px}nav{position:relative;width:auto;top:auto;bottom:auto;padding:10px 14px;flex-direction:row;flex-wrap:wrap;border-right:0;border-bottom:1px solid var(--line)}nav:before{width:100%;padding:4px 8px 8px}nav:after{display:none}nav a{font-size:.82rem;padding:9px 10px}main{margin:0;padding:26px 18px;min-height:auto}footer{margin-left:0;padding:18px} }
@media(max-width:520px){header{align-items:flex-start;flex-direction:column;gap:6px}.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.card,.panel{padding:16px}.metric{font-size:1.8rem}main{padding:22px 13px}nav a{padding:8px}}
</style></head><body>
<header><div><strong>School management</strong><br><span>Welcome to your Scholar Tracker workspace</span></div><div><span>● Demo workspace · Sample data</span></div></header>
<nav>
{% if session.get('role') == 'admin' %}
<a href="{{ url_for('dashboard') }}">Dashboard</a><a href="{{ url_for('students_page') }}">Students</a><a href="{{ url_for('attendance_page') }}">Lesson attendance</a><a href="{{ url_for('timetable_page') }}">Teachers timetable</a><a href="{{ url_for('admin_teachers') }}">Teacher accounts</a><a href="{{ url_for('reports') }}">Reports</a><a href="{{ url_for('calendar_page') }}">School calendar</a><a href="{{ url_for('notifications_page') }}">Parent notifications</a><a href="{{ url_for('parent_invitations') }}">Parent invitations</a><a href="{{ url_for('attendance_risk') }}">Attendance follow-up</a><a href="{{ url_for('unmarked_registers') }}">Unmarked registers</a><a href="{{ url_for('school_notices') }}">School notices</a><a href="{{ url_for('champion_tasks') }}">Champion tasks</a><a href="{{ url_for('audit_log') }}">Audit log</a><form method="post" action="{{ url_for('admin_logout') }}"><button type="submit">Admin logout</button></form>
{% elif session.get('role') == 'teacher' %}
<a href="{{ url_for('teacher_portal') }}">My lessons</a><form method="post" action="{{ url_for('teacher_logout') }}"><button type="submit">Teacher logout</button></form>
{% else %}
<a href="{{ url_for('admin_login') }}">Administrator login</a><a href="{{ url_for('teacher_login') }}">Teacher login</a>
{% endif %}
<a href="{{ url_for('parent_calendar') }}">Parent calendar view</a>
</nav>
<main>
{% for message in get_flashed_messages() %}<div class="flash">{{ message }}</div>{% endfor %}
{{ body|safe }}
</main><footer>Scholar Tracker · Built as a learning prototype for school attendance management.</footer></body></html>
"""

def page(title, body, **context):
    # Inject a server-generated CSRF token into every POST form rendered by this helper.
    body = re.sub(
        r'(<form\b[^>]*method="post"[^>]*>)',
        r'\1{{ csrf_field() }}',
        body,
        flags=re.IGNORECASE,
    )
    return render_template_string(
        PAGE,
        title=title,
        body=render_template_string(body, csrf_field=csrf_field, **context),
        csrf_field=csrf_field,
    )


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def teacher_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "teacher" or "teacher_user_id" not in session:
            flash("Please log in to access the teacher portal.")
            return redirect(url_for("teacher_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def admin_login():
    configured_username = os.environ.get("ADMIN_USERNAME", "").strip()
    configured_password = os.environ.get("ADMIN_PASSWORD", "")
    configured = bool(configured_username and len(configured_password) >= 16)
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if (
            configured
            and hmac.compare_digest(username, configured_username)
            and hmac.compare_digest(password, configured_password)
        ):
            session.clear()
            session["role"] = "admin"
            session["admin_username"] = configured_username
            session.permanent = True
            return redirect(url_for("dashboard"))
        flash("Login failed. Check your credentials or configure the administrator secrets in Render.")
    body = """
    <h1>Administrator login</h1>
    <p class="muted">Sign in to manage school records and settings.</p>
    {% if not configured %}<div class="notice"><strong>Administrator login is disabled.</strong><br>In Render, set ADMIN_USERNAME and a strong ADMIN_PASSWORD containing at least 16 characters. Also set SECRET_KEY to a long random secret.</div>{% endif %}
    <section class="panel" style="max-width:520px"><form method="post">
      <div class="field"><label>Administrator username</label><input name="username" autocomplete="username" required></div>
      <div class="field"><label>Password</label><input type="password" name="password" autocomplete="current-password" required></div>
      <button type="submit">Log in securely</button>
    </form></section>
    """
    return page("Administrator login", body, configured=configured)

@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("admin_login"))

@app.route("/admin/teachers", methods=["GET", "POST"])
@admin_required
def admin_teachers():
    with connect_db() as db:
        if request.method == "POST":
            action = request.form.get("action", "create")
            if action in ("activate", "deactivate"):
                try:
                    teacher_id = int(request.form.get("teacher_id", ""))
                    db.execute(
                        "UPDATE teacher_users SET active=? WHERE id=?",
                        (1 if action == "activate" else 0, teacher_id),
                    )
                    db.commit()
                    flash("Teacher account status updated.")
                except (ValueError, sqlite3.Error):
                    flash("Could not update that teacher account.")
                return redirect(url_for("admin_teachers"))
            username = request.form.get("username", "").strip()
            teacher_name = request.form.get("teacher_name", "").strip()
            password = request.form.get("password", "")
            if len(username) < 3 or not teacher_name or len(password) < 12:
                flash("Use a username of at least 3 characters, a teacher name, and a password of at least 12 characters.")
            elif username.casefold() == "teacher":
                flash("The reserved demo username is not allowed. Choose a named account.")
            else:
                try:
                    db.execute(
                        "INSERT INTO teacher_users(username, teacher_name, password_hash) VALUES(?,?,?)",
                        (username, teacher_name, generate_password_hash(password)),
                    )
                    db.commit()
                    flash("Teacher account created. Share the credentials privately with that teacher.")
                    return redirect(url_for("admin_teachers"))
                except sqlite3.IntegrityError:
                    flash("That username already exists.")
        teachers = db.execute(
            "SELECT id, username, teacher_name, active FROM teacher_users WHERE username != 'teacher' ORDER BY teacher_name"
        ).fetchall()
    body = """
    <h1>Teacher accounts</h1>
    <p class="muted">Create named accounts for staff. Never share accounts between teachers.</p>
    <section class="panel"><h2>Create teacher account</h2>
      <form method="post">
        <div class="field"><label>Username</label><input name="username" minlength="3" autocomplete="off" required></div>
        <div class="field"><label>Teacher's name</label><input name="teacher_name" required></div>
        <div class="field"><label>Temporary password (12+ characters)</label><input type="password" name="password" minlength="12" autocomplete="new-password" required></div>
        <button type="submit">Create account</button>
      </form>
    </section>
    <div class="table-wrap"><table><tr><th>Username</th><th>Teacher</th><th>Status</th><th>Action</th></tr>
    {% for t in teachers %}<tr><td>{{t.username}}</td><td>{{t.teacher_name}}</td><td>{{'Active' if t.active else 'Disabled'}}</td><td>
      <form method="post" style="margin:0"><input type="hidden" name="teacher_id" value="{{t.id}}"><input type="hidden" name="action" value="{{'deactivate' if t.active else 'activate'}}"><button type="submit">{{'Disable' if t.active else 'Activate'}}</button></form>
    </td></tr>{% endfor %}</table></div>
    """
    return page("Teacher accounts", body, teachers=teachers)

@app.route("/teacher/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def teacher_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with connect_db() as db:
            user = db.execute("SELECT * FROM teacher_users WHERE username=? AND active=1", (username,)).fetchone()
        if username.casefold() != "teacher" and user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["role"] = "teacher"
            session["teacher_user_id"] = user["id"]
            session["teacher_name"] = user["teacher_name"]
            session.permanent = True
            return redirect(url_for("teacher_portal"))
        flash("Login failed. The shared demo account is disabled; ask the school administrator for your own account.")
    body = """
    <h1>Teacher portal login</h1><p class="muted">Sign in to view your assigned lessons and mark a class register.</p>
    <section class="panel" style="max-width:520px"><form method="post">
      <div class="field"><label>Username</label><input name="username" autocomplete="username" required></div>
      <div class="field"><label>Password</label><input type="password" name="password" autocomplete="current-password" required></div>
      <button type="submit">Log in</button></form></section>"""
    return page("Teacher portal login", body)

@app.route("/teacher/logout", methods=["POST"])
def teacher_logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("teacher_login"))

@app.route("/teacher/portal")
@teacher_required
def teacher_portal():
    teacher_name = session["teacher_name"]
    chosen_date = request.args.get("lesson_date", date.today().isoformat())
    try:
        weekday = date.fromisoformat(chosen_date).strftime("%A")
    except ValueError:
        chosen_date = date.today().isoformat()
        weekday = date.today().strftime("%A")
    with connect_db() as db:
        lessons = db.execute("SELECT * FROM teacher_timetable WHERE teacher_name=? AND weekday=? ORDER BY start_time,period",
                             (teacher_name, weekday)).fetchall()
    body = """
    <div style="display:flex;justify-content:space-between;gap:14px;align-items:start;flex-wrap:wrap">
      <div><h1>Teacher portal</h1><p class="muted">Welcome, {{teacher_name}}. Your assigned lessons and class registers are below.</p></div>
      <form method="post" action="{{url_for('teacher_logout')}}" style="margin:0"><button type="submit">Log out</button></form>
    </div>
    <section class="panel"><form method="get"><div class="field"><label>Teaching date</label><input type="date" name="lesson_date" value="{{chosen_date}}" required></div><button>View day</button></form></section>
    {% if lessons %}<div class="table-wrap"><table><tr><th>Time</th><th>Subject</th><th>Class / stream</th><th>Room</th><th>Register</th></tr>
    {% for lesson in lessons %}<tr><td>{{lesson.start_time}}–{{lesson.end_time}}</td><td>{{lesson.subject}}</td><td>{{lesson.class_name}} / {{lesson.stream}}</td><td>{{lesson.room or '—'}}</td><td><a class="btn" href="{{url_for('teacher_register',lesson_id=lesson.id,lesson_date=chosen_date)}}">Mark register</a></td></tr>{% endfor %}</table></div>
    {% else %}<section class="panel"><p>No lessons assigned to your account for {{weekday}}. Ask the school administrator to add your teacher name to the timetable as <strong>{{teacher_name}}</strong>.</p><a href="{{url_for('timetable_page')}}" class="btn">Open timetable</a></section>{% endif %}
    <p class="muted">Prototype only: do not enter real student data until school access controls and persistent storage are configured.</p>"""
    return page("Teacher portal", body, teacher_name=teacher_name, chosen_date=chosen_date, weekday=weekday, lessons=lessons)

@app.route("/teacher/register/<int:lesson_id>", methods=["GET", "POST"])
@teacher_required
def teacher_register(lesson_id):
    chosen_date = request.values.get("lesson_date", date.today().isoformat())
    teacher_name = session["teacher_name"]
    try:
        date.fromisoformat(chosen_date)
    except ValueError:
        chosen_date = date.today().isoformat()
    with connect_db() as db:
        lesson = db.execute("SELECT * FROM teacher_timetable WHERE id=? AND teacher_name=?", (lesson_id, teacher_name)).fetchone()
        if not lesson:
            flash("That lesson is not assigned to your teacher account.")
            return redirect(url_for("teacher_portal", lesson_date=chosen_date))
        if request.method == "POST":
            students = db.execute("SELECT id FROM students WHERE class_name=? AND stream=? ORDER BY full_name",
                                  (lesson["class_name"], lesson["stream"])).fetchall()
            for student in students:
                status = request.form.get("status_" + str(student["id"]), "Absent")
                if status not in ("Present", "Absent", "Late"):
                    status = "Absent"
                reason_code = request.form.get("reason_" + str(student["id"]), "Unknown")
                allowed_reasons = {"Illness", "Family responsibility", "Transport problem", "Fees-related issue", "School anxiety or bullying concern", "Unknown / needs follow-up"}
                if status != "Absent" or reason_code not in allowed_reasons:
                    reason_code = "Unknown / needs follow-up"
                db.execute("""INSERT INTO attendance(student_id,lesson_date,subject,status,marked_by,reason_code)
                              VALUES(?,?,?,?,?,?) ON CONFLICT(student_id,lesson_date,subject)
                              DO UPDATE SET status=excluded.status,marked_by=excluded.marked_by,reason_code=excluded.reason_code""",
                           (student["id"], chosen_date, lesson["subject"], status, teacher_name, reason_code))
                # Record an in-app demo alert when a teacher marks a learner absent.
                # This is a notification log only; it does not send SMS/email/push messages.
                if status == "Absent":
                    parent = db.execute(
                        "SELECT full_name, parent_contact FROM students WHERE id=?",
                        (student["id"],),
                    ).fetchone()
                    if parent and parent["parent_contact"]:
                        db.execute(
                            "INSERT INTO notifications(recipient, message, status) VALUES(?,?,?)",
                            (
                                parent["parent_contact"],
                                f"Demo alert: {parent['full_name']} was marked absent for "
                                f"{lesson['subject']} on {chosen_date} by {teacher_name}.",
                                "Demo only — not sent",
                            ),
                        )
            db.commit()
            flash("Class register saved. Any absence alerts were added to the demo notification log only.")
            return redirect(url_for("teacher_register", lesson_id=lesson_id, lesson_date=chosen_date))
        students = db.execute("SELECT * FROM students WHERE class_name=? AND stream=? ORDER BY full_name",
                              (lesson["class_name"], lesson["stream"])).fetchall()
        saved = db.execute("""SELECT a.student_id,a.status FROM attendance a JOIN students s ON s.id=a.student_id
                              WHERE a.lesson_date=? AND a.subject=? AND s.class_name=? AND s.stream=?""",
                           (chosen_date, lesson["subject"], lesson["class_name"], lesson["stream"])).fetchall()
        saved_map = {r["student_id"]: r["status"] for r in saved}
    body = """
    <h1>Mark class register</h1><p class="muted">{{lesson.subject}} · {{lesson.class_name}} / {{lesson.stream}} · {{lesson.start_time}}–{{lesson.end_time}}</p>
    <section class="panel"><form method="get"><div class="field"><label>Lesson date</label><input type="date" name="lesson_date" value="{{chosen_date}}" required></div><button>Load date</button></form></section>
    {% if students %}<form method="post"><input type="hidden" name="lesson_date" value="{{chosen_date}}">
      <p><button type="button" onclick="document.querySelectorAll('[name^=status_]').forEach(function(x){x.value='Present'})">Mark all present</button> <span class="muted">Review any absent or late learners before saving.</span></p>
      <div class="table-wrap"><table><tr><th>Admission no.</th><th>Student</th><th>Attendance</th><th>Confidential reason category (absent only)</th></tr>
      {% for s in students %}<tr><td>{{s.admission_no}}</td><td>{{s.full_name}}</td><td><select name="status_{{s.id}}">{% for status in ['Present','Absent','Late'] %}<option {% if saved_map.get(s.id,'Present')==status %}selected{% endif %}>{{status}}</option>{% endfor %}</select></td><td><select name="reason_{{s.id}}"><option>Unknown / needs follow-up</option><option>Illness</option><option>Family responsibility</option><option>Transport problem</option><option>Fees-related issue</option><option>School anxiety or bullying concern</option></select></td></tr>{% endfor %}</table></div>
      <p><button type="submit">Save class register</button> <a href="{{url_for('teacher_portal',lesson_date=chosen_date)}}">Back to teacher portal</a></p>
    </form>{% else %}<p>No students found in this class and stream. Ask the administrator to check the class and stream.</p>{% endif %}"""
    return page("Mark class register", body, lesson=lesson, chosen_date=chosen_date, students=students, saved_map=saved_map)

@app.route("/")
@admin_required
def dashboard():
    with connect_db() as db:
        students = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        today = date.today().isoformat()
        rows = db.execute("SELECT status, COUNT(*) n FROM attendance WHERE lesson_date=? GROUP BY status", (today,)).fetchall()
        stats = {r["status"]: r["n"] for r in rows}
        recent = db.execute("""SELECT a.lesson_date,a.subject,a.status,s.full_name,s.class_name
            FROM attendance a JOIN students s ON s.id=a.student_id
            ORDER BY a.lesson_date DESC,a.id DESC LIMIT 8""").fetchall()
        events = db.execute("SELECT * FROM events WHERE event_date>=? ORDER BY event_date LIMIT 5", (today,)).fetchall()
    body = """
    <h1>School overview</h1><p class="muted">A simple view of attendance and school activity.</p>
    <div class="cards">
      <div class="card"><span class="muted">Registered students</span><div class="metric">{{ students }}</div></div>
      <div class="card"><span class="muted">Present today</span><div class="metric">{{ stats.get('Present',0) }}</div></div>
      <div class="card"><span class="muted">Absent today</span><div class="metric">{{ stats.get('Absent',0) }}</div></div>
      <div class="card"><span class="muted">Late today</span><div class="metric">{{ stats.get('Late',0) }}</div></div>
    </div>
    <div class="notice">Demo database contains sample students. Replace these with authorised school data before using the app in a real school.</div>
    <div class="grid"><section class="panel"><h2>Recent lesson attendance</h2>
    {% if recent %}<div class="table-wrap"><table><tr><th>Date</th><th>Student</th><th>Subject</th><th>Status</th></tr>
    {% for r in recent %}<tr><td>{{r.lesson_date}}</td><td>{{r.full_name}}</td><td>{{r.subject}}</td><td><span class="pill">{{r.status}}</span></td></tr>{% endfor %}</table></div>
    {% else %}<p class="muted">No attendance has been recorded yet.</p>{% endif %}</section>
    <section class="panel"><h2>Upcoming calendar events</h2>{% if events %}{% for e in events %}<p><strong>{{e.event_date}}</strong> — {{e.title}}<br><span class="muted">{{e.details}}</span></p>{% endfor %}{% else %}<p class="muted">No events added yet.</p>{% endif %}
    <a class="btn" href="{{url_for('calendar_page')}}">Manage calendar</a></section></div>
    """
    return page("Dashboard", body, students=students, stats=stats, recent=recent, events=events)

@app.route("/students", methods=["GET","POST"])
@admin_required
def students_page():
    with connect_db() as db:
        if request.method == "POST":
            admission = request.form.get("admission_no","").strip()
            name = request.form.get("full_name","").strip()
            cls = request.form.get("class_name","").strip()
            stream = request.form.get("stream","A").strip() or "A"
            contact = request.form.get("parent_contact","").strip()
            if not admission or not name or not cls:
                flash("Admission number, student name and class are required.")
            else:
                try:
                    db.execute("INSERT INTO students(admission_no,full_name,class_name,stream,parent_contact) VALUES(?,?,?,?,?)",(admission,name,cls,stream,contact))
                    db.commit()
                    flash("Student added successfully.")
                    return redirect(url_for("students_page"))
                except sqlite3.IntegrityError:
                    flash("That admission number already exists.")
        students = db.execute("SELECT * FROM students ORDER BY class_name,stream,full_name").fetchall()
    body = """
    <h1>Students</h1><p class="muted">Register learners and organise them by class and stream.</p>
    <section class="panel"><h2>Add a student</h2><form method="post">
    <div class="field"><label>Admission number *</label><input name="admission_no" required></div>
    <div class="field"><label>Full name *</label><input name="full_name" required></div>
    <div class="field"><label>Class *</label><input name="class_name" placeholder="Form 1" required></div>
    <div class="field"><label>Stream</label><input name="stream" value="A"></div>
    <div class="field"><label>Parent contact (optional)</label><input name="parent_contact"></div><button>Add student</button></form></section>
    <div class="table-wrap"><table><tr><th>Admission no.</th><th>Student</th><th>Class</th><th>Stream</th></tr>
    {% for s in students %}<tr><td>{{s.admission_no}}</td><td>{{s.full_name}}</td><td>{{s.class_name}}</td><td>{{s.stream}}</td></tr>{% endfor %}</table></div>
    """
    return page("Students", body, students=students)

@app.route("/attendance", methods=["GET","POST"])
@admin_required
def attendance_page():
    chosen_date = request.values.get("lesson_date", date.today().isoformat())
    chosen_class = request.values.get("class_name", "")
    subject = request.values.get("subject", "General").strip() or "General"
    with connect_db() as db:
        classes = [r["class_name"] for r in db.execute("SELECT DISTINCT class_name FROM students ORDER BY class_name").fetchall()]
        if chosen_class not in classes and classes:
            chosen_class = classes[0]
        if request.method == "POST":
            ids = db.execute("SELECT id FROM students WHERE class_name=? ORDER BY id", (chosen_class,)).fetchall()
            for row in ids:
                status = request.form.get("status_"+str(row["id"]), "Absent")
                if status not in ("Present","Absent","Late"):
                    status = "Absent"
                db.execute("""INSERT INTO attendance(student_id,lesson_date,subject,status,marked_by)
                    VALUES(?,?,?,?,?) ON CONFLICT(student_id,lesson_date,subject)
                    DO UPDATE SET status=excluded.status,marked_by=excluded.marked_by""",
                    (row["id"], chosen_date, subject, status, request.form.get("marked_by","Teacher").strip() or "Teacher"))
                if status == "Absent":
                    student = db.execute("SELECT full_name,parent_contact FROM students WHERE id=?", (row["id"],)).fetchone()
                    if student and student["parent_contact"]:
                        db.execute("INSERT INTO notifications(recipient,message) VALUES(?,?)",
                                   (student["parent_contact"], f"Demo alert: {student['full_name']} was marked absent for {subject} on {chosen_date}."))
            db.commit()
            flash("Attendance saved. Parent alerts are recorded as demos only; no messages were sent.")
            return redirect(url_for("attendance_page", lesson_date=chosen_date, class_name=chosen_class, subject=subject))
        students = db.execute("SELECT * FROM students WHERE class_name=? ORDER BY stream,full_name", (chosen_class,)).fetchall()
        saved = db.execute("SELECT student_id,status FROM attendance WHERE lesson_date=? AND subject=?", (chosen_date,subject)).fetchall()
        saved_map = {r["student_id"]:r["status"] for r in saved}
    body = """
    <h1>Lesson attendance</h1><p class="muted">Choose a class and subject, then record each learner's status.</p>
    <section class="panel"><form method="get">
      <div class="field"><label>Date</label><input type="date" name="lesson_date" value="{{chosen_date}}" required></div>
      <div class="field"><label>Class</label><select name="class_name">{% for c in classes %}<option {% if c==chosen_class %}selected{% endif %}>{{c}}</option>{% endfor %}</select></div>
      <div class="field"><label>Subject / lesson</label><input name="subject" value="{{subject}}" required></div><button>Load class</button></form></section>
    {% if students %}<form method="post"><input type="hidden" name="lesson_date" value="{{chosen_date}}"><input type="hidden" name="class_name" value="{{chosen_class}}"><input type="hidden" name="subject" value="{{subject}}">
    <div class="field"><label>Teacher name</label><input name="marked_by" value="Teacher"></div>
    <div class="table-wrap"><table><tr><th>Student</th><th>Stream</th><th>Attendance status</th></tr>
    {% for s in students %}<tr><td>{{s.full_name}} <span class="muted">({{s.admission_no}})</span></td><td>{{s.stream}}</td><td><select name="status_{{s.id}}">{% for status in ['Present','Absent','Late'] %}<option {% if saved_map.get(s.id,'Present')==status %}selected{% endif %}>{{status}}</option>{% endfor %}</select></td></tr>{% endfor %}</table></div><p><button>Save attendance</button></p></form>
    {% else %}<p>No students in this class yet. Add students first.</p>{% endif %}
    """
    return page("Lesson attendance", body, classes=classes, students=students, saved_map=saved_map,
                chosen_date=chosen_date, chosen_class=chosen_class, subject=subject)

@app.route("/timetable", methods=["GET", "POST"])
@admin_required
def timetable_page():
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    selected_day = request.values.get("weekday", date.today().strftime("%A"))
    if selected_day not in weekdays:
        selected_day = "Monday"
    selected_teacher = request.values.get("teacher_name", "").strip()
    selected_class = request.values.get("class_name", "").strip()
    with connect_db() as db:
        if request.method == "POST" and request.form.get("delete_id"):
            try:
                lesson_id = int(request.form.get("delete_id"))
                db.execute("DELETE FROM teacher_timetable WHERE id=?", (lesson_id,))
                db.commit()
                flash("Timetable lesson deleted.")
                return redirect(url_for("timetable_page", weekday=selected_day, teacher_name=selected_teacher, class_name=selected_class))
            except (ValueError, sqlite3.Error):
                flash("Could not delete that timetable entry.")
        elif request.method == "POST":
            weekday = request.form.get("weekday", "").strip()
            teacher = request.form.get("teacher_name", "").strip()
            subject = request.form.get("subject", "").strip()
            class_name = request.form.get("class_name", "").strip()
            stream = request.form.get("stream", "A").strip() or "A"
            room = request.form.get("room", "").strip()
            start_time = request.form.get("start_time", "").strip()
            end_time = request.form.get("end_time", "").strip()
            try:
                period = int(request.form.get("period", "1"))
            except ValueError:
                period = 0
            if weekday not in weekdays or not teacher or not subject or not class_name or not start_time or not end_time or period < 1:
                flash("Please complete all required timetable fields.")
            elif start_time >= end_time:
                flash("Lesson end time must be later than its start time.")
            else:
                conflict = db.execute(
                    """SELECT teacher_name, subject, class_name, stream, room, start_time, end_time
                       FROM teacher_timetable
                       WHERE weekday=? AND start_time < ? AND end_time > ?
                         AND (teacher_name=? OR (class_name=? AND stream=?) OR (? != '' AND room=?))
                       LIMIT 1""",
                    (weekday, end_time, start_time, teacher, class_name, stream, room, room)
                ).fetchone()
                if conflict:
                    flash("Timetable conflict: this teacher, class/stream, or room is already booked during that time.")
                else:
                    db.execute(
                        """INSERT INTO teacher_timetable
                           (weekday, period, start_time, end_time, teacher_name, subject, class_name, stream, room)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (weekday, period, start_time, end_time, teacher, subject, class_name, stream, room)
                    )
                    db.commit()
                    flash("Lesson added to the teachers timetable.")
                    return redirect(url_for("timetable_page", weekday=weekday, teacher_name=teacher))
        teachers = [r["teacher_name"] for r in db.execute("SELECT DISTINCT teacher_name FROM teacher_timetable ORDER BY teacher_name").fetchall()]
        classes = [r["class_name"] for r in db.execute("SELECT DISTINCT class_name FROM teacher_timetable ORDER BY class_name").fetchall()]
        sql = "SELECT * FROM teacher_timetable WHERE weekday=?"
        params = [selected_day]
        if selected_teacher:
            sql += " AND teacher_name=?"
            params.append(selected_teacher)
        if selected_class:
            sql += " AND class_name=?"
            params.append(selected_class)
        sql += " ORDER BY start_time, period, teacher_name"
        lessons = db.execute(sql, params).fetchall()
    body = """
    <h1>Teachers timetable</h1>
    <p class="muted">Plan lessons by day, teacher, subject, class and stream. The view defaults to one day instead of displaying the entire school timetable at once.</p>
    <section class="panel">
      <h2>Add a lesson</h2>
      <form method="post">
        <div class="field"><label>Day *</label><select name="weekday" required>{% for d in weekdays %}<option {% if d==selected_day %}selected{% endif %}>{{d}}</option>{% endfor %}</select></div>
        <div class="field"><label>Period number *</label><input type="number" name="period" min="1" max="20" value="1" required></div>
        <div class="field"><label>Start time *</label><input type="time" name="start_time" required></div>
        <div class="field"><label>End time *</label><input type="time" name="end_time" required></div>
        <div class="field"><label>Teacher name *</label><input name="teacher_name" placeholder="e.g. Mr. Otieno" required></div>
        <div class="field"><label>Subject *</label><input name="subject" placeholder="e.g. Mathematics" required></div>
        <div class="field"><label>Class *</label><input name="class_name" placeholder="e.g. Form 2" required></div>
        <div class="field"><label>Stream</label><input name="stream" value="A"></div>
        <div class="field"><label>Room (optional)</label><input name="room" placeholder="e.g. Room 4"></div>
        <button type="submit">Add lesson</button>
      </form>
    </section>
    <section class="panel" style="margin-top:16px">
      <h2>View timetable</h2>
      <form method="get">
        <div class="field"><label>Day</label><select name="weekday">{% for d in weekdays %}<option {% if d==selected_day %}selected{% endif %}>{{d}}</option>{% endfor %}</select></div>
        <div class="field"><label>Teacher</label><select name="teacher_name"><option value="">All teachers</option>{% for t in teachers %}<option value="{{t}}" {% if t==selected_teacher %}selected{% endif %}>{{t}}</option>{% endfor %}</select></div>
        <div class="field"><label>Class</label><select name="class_name"><option value="">All classes</option>{% for c in classes %}<option value="{{c}}" {% if c==selected_class %}selected{% endif %}>{{c}}</option>{% endfor %}</select></div>
        <button type="submit">Filter timetable</button>
      </form>
      {% if lessons %}
      <div class="table-wrap"><table><tr><th>Period</th><th>Time</th><th>Teacher</th><th>Subject</th><th>Class / stream</th><th>Room</th><th>Action</th></tr>
      {% for lesson in lessons %}
      <tr><td>{{lesson.period}}</td><td>{{lesson.start_time}}–{{lesson.end_time}}</td><td>{{lesson.teacher_name}}</td><td>{{lesson.subject}}</td><td>{{lesson.class_name}} / {{lesson.stream}}</td><td>{{lesson.room or '—'}}</td><td><form method="post" style="margin:0"><input type="hidden" name="delete_id" value="{{lesson.id}}"><input type="hidden" name="weekday" value="{{selected_day}}"><input type="hidden" name="teacher_name" value="{{selected_teacher}}"><input type="hidden" name="class_name" value="{{selected_class}}"><button type="submit" style="background:#e5484d;box-shadow:none;padding:7px 10px">Delete</button></form></td></tr>
      {% endfor %}</table></div>
      {% else %}<p class="muted">No lessons saved for this day and filter yet. Use “Add a lesson” above to build the timetable.</p>{% endif %}
    </section>
    <p class="muted">Demo feature: timetable entries are stored in this app's database. Add only sample information until account access and persistent storage are configured.</p>
    """
    return page("Teachers timetable", body, weekdays=weekdays, selected_day=selected_day,
                selected_teacher=selected_teacher, selected_class=selected_class,
                teachers=teachers, classes=classes, lessons=lessons)

@app.route("/reports")
@admin_required
def reports():
    start = request.args.get("start", date.today().replace(day=1).isoformat())
    end = request.args.get("end", date.today().isoformat())
    with connect_db() as db:
        rows = db.execute("""SELECT s.admission_no,s.full_name,s.class_name,s.stream,
            COUNT(a.id) lessons,
            SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) present,
            SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) absent,
            SUM(CASE WHEN a.status='Late' THEN 1 ELSE 0 END) late
            FROM students s LEFT JOIN attendance a ON a.student_id=s.id AND a.lesson_date BETWEEN ? AND ?
            GROUP BY s.id ORDER BY s.class_name,s.full_name""",(start,end)).fetchall()
    body = """
    <h1>Attendance reports</h1><p class="muted">Summary by student for the selected date range.</p>
    <section class="panel"><form method="get"><div class="field"><label>From</label><input type="date" name="start" value="{{start}}" required></div><div class="field"><label>To</label><input type="date" name="end" value="{{end}}" required></div><button>Generate report</button></form></section>
    <div class="table-wrap"><table><tr><th>Student</th><th>Class</th><th>Lessons marked</th><th>Present</th><th>Absent</th><th>Late</th><th>Present %</th></tr>
    {% for r in rows %}<tr><td>{{r.full_name}}</td><td>{{r.class_name}} {{r.stream}}</td><td>{{r.lessons}}</td><td>{{r.present or 0}}</td><td>{{r.absent or 0}}</td><td>{{r.late or 0}}</td><td>{% if r.lessons %}{{ ((r.present or 0)*100/r.lessons)|round(1) }}%{% else %}—{% endif %}</td></tr>{% endfor %}</table></div>
    <p class="muted">Reports reflect only records entered in this prototype; they are not evidence of tested school outcomes.</p>
    """
    return page("Reports", body, rows=rows, start=start, end=end)

@app.route("/calendar", methods=["GET","POST"])
@admin_required
def calendar_page():
    with connect_db() as db:
        if request.method == "POST":
            event_date = request.form.get("event_date","").strip()
            title = request.form.get("title","").strip()
            details = request.form.get("details","").strip()
            if not event_date or not title:
                flash("Event date and title are required.")
            else:
                db.execute("INSERT INTO events(event_date,title,details) VALUES(?,?,?)",(event_date,title,details))
                db.commit()
                flash("Calendar event added.")
                return redirect(url_for("calendar_page"))
        events = db.execute("SELECT * FROM events ORDER BY event_date DESC").fetchall()
    body = """
    <h1>School calendar</h1><p class="muted">Record school events, examinations, meetings and holidays.</p>
    <section class="panel"><h2>Add event</h2><form method="post"><div class="field"><label>Date</label><input type="date" name="event_date" required></div><div class="field"><label>Event title</label><input name="title" required></div><div class="field"><label>Details</label><input name="details"></div><button>Add event</button></form></section>
    <div class="table-wrap"><table><tr><th>Date</th><th>Event</th><th>Details</th></tr>{% for e in events %}<tr><td>{{e.event_date}}</td><td>{{e.title}}</td><td>{{e.details}}</td></tr>{% endfor %}</table></div>
    """
    return page("School calendar", body, events=events)

@app.route("/parents/calendar")
def parent_calendar():
    """Read-only calendar page for families; no student records are shown."""
    with connect_db() as db:
        events = db.execute("SELECT event_date, title, details FROM events ORDER BY event_date ASC").fetchall()
    body = """
    <h1>School calendar for parents</h1>
    <p class="muted">View upcoming school events, examinations, meetings and holidays.</p>
    <div class="notice">This is a read-only calendar view. It does not display student attendance or private student information.</div>
    {% if events %}<div class="table-wrap"><table><tr><th>Date</th><th>Event</th><th>Details</th></tr>
    {% for e in events %}<tr><td>{{e.event_date}}</td><td>{{e.title}}</td><td>{{e.details or "—"}}</td></tr>{% endfor %}
    </table></div>{% else %}<section class="panel"><p>No school events have been published yet. Please check again later.</p></section>{% endif %}
    <p class="muted">Prototype notice: events are only as current as the information entered by the school.</p>
    """
    return page("School calendar for parents", body, events=events)

@app.route("/notifications")
@admin_required
def notifications_page():
    with connect_db() as db:
        rows = db.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 100").fetchall()
    body = """
    <h1>Parent notifications</h1><p class="muted">Preview attendance alerts generated when a student with a parent contact is marked absent.</p>
    <div class="notice">Prototype limitation: these are stored in the app only. SMS, email and push notifications are not connected, and no messages are sent.</div>
    {% if rows %}<div class="table-wrap"><table><tr><th>Created</th><th>Recipient</th><th>Message</th><th>Status</th></tr>{% for r in rows %}<tr><td>{{r.created_at}}</td><td>{{r.recipient}}</td><td>{{r.message}}</td><td>{{r.status}}</td></tr>{% endfor %}</table></div>{% else %}<p class="muted">No demo notifications yet. Add a parent contact to a student, then mark that student absent.</p>{% endif %}
    """
    return page("Parent notifications", body, rows=rows)

@app.route("/health")
def health():
    return {"status":"ok","app":"Scholar Tracker"}

from resilience import register_resilience_routes, init_resilience_db
from parent_portal import init_parent_portal_db, register_parent_portal

init_db()
init_resilience_db(connect_db)
init_parent_portal_db(connect_db)
register_resilience_routes(app, connect_db, admin_required, teacher_required, page)
register_parent_portal(app, connect_db, admin_required, limiter, csrf_field, page)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
