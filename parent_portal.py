"""Secure parent portal for Scholar Tracker.

Parent accounts are created only from single-use, expiring email invitations.
Every child-specific query is scoped by parent ID, school ID, and an active
parent-child link. Email delivery is fail-closed when SMTP is not configured.
"""
import hashlib
import os
import re
import secrets
import smtplib
import ssl
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps

from flask import abort, flash, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PARENT_LAYOUT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>{{ title }} · Scholar Tracker</title>
<style>
body{margin:0;background:#f4f7fc;color:#17243b;font:15px system-ui,-apple-system,Segoe UI,sans-serif}
header{background:#fff;border-bottom:1px solid #e3e8f1;padding:18px clamp(16px,4vw,48px);display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
main{max-width:1080px;margin:30px auto;padding:0 16px 40px}h1{letter-spacing:-.04em;margin:0 0 8px}h2{font-size:1.05rem}p{line-height:1.6}.muted{color:#66748b}.panel{background:white;border:1px solid #e3e8f1;border-radius:16px;padding:22px;margin:16px 0;box-shadow:0 6px 24px #1e31500a}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}.metric{font-size:1.8rem;font-weight:800;margin-top:8px}
form{display:flex;flex-wrap:wrap;align-items:end;gap:12px;margin:14px 0}.field{display:flex;flex-direction:column;gap:6px;min-width:200px;flex:1}label{font-size:.83rem;font-weight:700;color:#52617a}
input,textarea{font:inherit;padding:11px 12px;border:1px solid #ccd5e4;border-radius:9px;max-width:100%}button,.btn{font:inherit;font-weight:750;border:0;border-radius:9px;padding:11px 15px;background:#345de7;color:white;text-decoration:none;cursor:pointer;display:inline-block}
.secondary{background:#edf1ff;color:#294bc3}.notice{background:#edf2ff;color:#314d95;padding:13px 15px;border-radius:10px;margin:14px 0}.error{background:#fff0ef;color:#8e2922;padding:13px 15px;border-radius:10px;margin:14px 0}
table{width:100%;border-collapse:collapse;background:#fff}th,td{text-align:left;padding:12px;border-bottom:1px solid #e7ebf2;vertical-align:top}th{font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;color:#68758c;background:#f8f9fc}.table-wrap{overflow-x:auto;border:1px solid #e3e8f1;border-radius:12px;margin:12px 0}
nav{display:flex;gap:10px;flex-wrap:wrap}a{color:#345de7}small{color:#6b7890}
</style></head><body>
<header><div><strong>🎓 Scholar Tracker · Parent Portal</strong><br><small>Private family access</small></div>
<nav>{% if session.get('role') == 'parent' %}<a href="{{ url_for('parent_portal') }}">Overview</a><a href="{{ url_for('parent_calendar') }}">School calendar</a><a href="{{ url_for('parent_notices') }}">Notices</a><a href="{{ url_for('parent_privacy') }}">Privacy</a><form method="post" action="{{ url_for('parent_logout') }}" style="margin:0">{{ csrf_field() }}<button class="secondary" type="submit">Log out</button></form>{% else %}<a href="{{ url_for('parent_login') }}">Parent sign in</a>{% endif %}</nav></header>
<main>{% for message in get_flashed_messages() %}<div class="notice">{{ message }}</div>{% endfor %}{{ body|safe }}</main></body></html>"""


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(value):
    return (value or "").strip().lower()


def send_email(recipient, subject, body):
    """Send email using environment-configured SMTP; return False if unavailable."""
    host = os.environ.get("SMTP_HOST", "").strip()
    sender = os.environ.get("SMTP_FROM", "").strip()
    if not host or not sender:
        return False
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        message = EmailMessage()
        message["From"] = sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            username = os.environ.get("SMTP_USERNAME", "").strip()
            password = os.environ.get("SMTP_PASSWORD", "")
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return True
    except (OSError, ValueError, smtplib.SMTPException):
        return False


def init_parent_portal_db(connect_db):
    """Create parent tables and safely migrate existing single-school records."""
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS schools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT OR IGNORE INTO schools(id,name) VALUES(1,'Scholar Tracker Demo School');
        CREATE TABLE IF NOT EXISTS parent_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL REFERENCES schools(id),
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            email_verified_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            session_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            password_changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS parent_invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL REFERENCES schools(id),
            student_id INTEGER NOT NULL REFERENCES students(id),
            email TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT DEFAULT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS parent_student_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL REFERENCES parent_accounts(id),
            student_id INTEGER NOT NULL REFERENCES students(id),
            school_id INTEGER NOT NULL REFERENCES schools(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revoked_at TEXT DEFAULT NULL,
            UNIQUE(parent_id, student_id)
        );
        CREATE TABLE IF NOT EXISTS parent_password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL REFERENCES parent_accounts(id),
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_parent_links_scope
            ON parent_student_links(parent_id, school_id, revoked_at, student_id);
        CREATE INDEX IF NOT EXISTS idx_parent_invite_lookup
            ON parent_invitations(token_hash, used_at, expires_at);
        CREATE INDEX IF NOT EXISTS idx_parent_reset_lookup
            ON parent_password_resets(token_hash, used_at, expires_at);
        """)
        for table in ("students", "events", "school_notices"):
            columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
            if "school_id" not in columns:
                db.execute(f"ALTER TABLE {table} ADD COLUMN school_id INTEGER NOT NULL DEFAULT 1")
        db.execute("CREATE INDEX IF NOT EXISTS idx_students_school ON students(school_id, id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_events_school_date ON events(school_id, event_date)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_notices_school_published ON school_notices(school_id, published, created_at)")
        db.commit()


def register_parent_portal(app, connect_db, admin_required, limiter, csrf_field, page):
    def parent_page(title, body, **context):
        rendered = render_template_string(body, csrf_field=csrf_field, **context)
        return render_template_string(PARENT_LAYOUT, title=title, body=rendered, csrf_field=csrf_field)

    def parent_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("role") != "parent" or not session.get("parent_id"):
                return redirect(url_for("parent_login", next=request.path))
            with connect_db() as db:
                account = db.execute(
                    "SELECT id, school_id, active, session_version FROM parent_accounts WHERE id=?",
                    (session.get("parent_id"),),
                ).fetchone()
            if (
                not account
                or not account["active"]
                or account["school_id"] != session.get("parent_school_id")
                or account["session_version"] != session.get("parent_session_version")
            ):
                session.clear()
                return redirect(url_for("parent_login"))
            return view(*args, **kwargs)
        return wrapped

    def active_invitation(db, raw_token):
        if not raw_token or len(raw_token) > 200:
            return None
        return db.execute(
            """SELECT i.id,i.school_id,i.student_id,i.email,i.expires_at,
                      s.full_name,s.class_name,s.stream
               FROM parent_invitations i
               JOIN students s ON s.id=i.student_id AND s.school_id=i.school_id
               WHERE i.token_hash=? AND i.used_at IS NULL AND i.expires_at>?""",
            (token_digest(raw_token), utcnow()),
        ).fetchone()

    def login_parent(account):
        session.clear()
        session["role"] = "parent"
        session["parent_id"] = account["id"]
        session["parent_school_id"] = account["school_id"]
        session["parent_session_version"] = account["session_version"]
        session.permanent = True

    @app.route("/parents/login", methods=["GET", "POST"])
    @limiter.limit("5 per minute")
    def parent_login():
        if request.method == "POST":
            email = normalize_email(request.form.get("email"))
            password = request.form.get("password", "")
            with connect_db() as db:
                account = db.execute(
                    """SELECT id,school_id,password_hash,active,session_version
                       FROM parent_accounts WHERE email=? AND email_verified_at IS NOT NULL""",
                    (email,),
                ).fetchone()
            if account and account["active"] and check_password_hash(account["password_hash"], password):
                login_parent(account)
                return redirect(url_for("parent_portal"))
            flash("Sign-in failed. Check your email and password, or use password reset.")
        body = """
        <h1>Parent sign in</h1><p class="muted">Use the email address that received your school invitation.</p>
        <section class="panel" style="max-width:560px"><form method="post">
          {{ csrf_field() }}<div class="field"><label>Email address</label><input type="email" name="email" autocomplete="username" maxlength="254" required></div>
          <div class="field"><label>Password</label><input type="password" name="password" autocomplete="current-password" maxlength="256" required></div>
          <button type="submit">Sign in</button></form><p><a href="{{ url_for('parent_forgot_password') }}">Forgot password?</a></p></section>
        """
        return parent_page("Parent sign in", body)

    @app.route("/parents/accept-invitation", methods=["GET", "POST"])
    @limiter.limit("10 per minute")
    def parent_accept_invitation():
        token = request.values.get("token", "")
        with connect_db() as db:
            invitation = active_invitation(db, token)
            if not invitation:
                return parent_page(
                    "Invitation unavailable",
                    "<h1>Invitation unavailable</h1><p class='error'>This invitation is invalid, expired, or already used. Ask the school to issue a new one.</p>",
                ), 400
            existing = db.execute(
                "SELECT id,school_id,password_hash,active,session_version FROM parent_accounts WHERE email=?",
                (invitation["email"],),
            ).fetchone()
        if request.method == "GET":
            if existing and existing["school_id"] != invitation["school_id"]:
                return parent_page("Invitation unavailable", "<h1>Invitation unavailable</h1><p class='error'>Please contact the school office for help with this invitation.</p>"), 400
            if existing:
                body = """
                <h1>Confirm parent account</h1><p class="muted">This invitation is for the already registered email <strong>{{ email }}</strong> and learner <strong>{{ student }}</strong>.</p>
                <section class="panel" style="max-width:600px"><form method="post">
                  {{ csrf_field() }}<input type="hidden" name="token" value="{{ token }}">
                  <div class="field"><label>Current parent password</label><input type="password" name="current_password" autocomplete="current-password" required maxlength="256"></div>
                  <button type="submit">Link learner to my account</button></form></section>
                """
            else:
                body = """
                <h1>Activate parent account</h1><p class="muted">The invitation verifies control of <strong>{{ email }}</strong> and is linked to learner <strong>{{ student }}</strong>.</p>
                <section class="panel" style="max-width:600px"><form method="post">
                  {{ csrf_field() }}<input type="hidden" name="token" value="{{ token }}">
                  <div class="field"><label>Create password (12 or more characters)</label><input type="password" name="password" autocomplete="new-password" minlength="12" maxlength="256" required></div>
                  <div class="field"><label>Confirm password</label><input type="password" name="confirm_password" autocomplete="new-password" minlength="12" maxlength="256" required></div>
                  <button type="submit">Activate parent account</button></form></section>
                """
            return parent_page("Accept parent invitation", body, email=invitation["email"], student=invitation["full_name"], token=token)

        now = utcnow()
        with connect_db() as db:
            db.execute("BEGIN IMMEDIATE")
            invitation = active_invitation(db, token)
            if not invitation:
                db.rollback()
                return parent_page("Invitation unavailable", "<h1>Invitation unavailable</h1><p class='error'>This invitation is invalid, expired, or already used. Ask the school to issue a new one.</p>"), 400
            account = db.execute(
                "SELECT id,school_id,password_hash,active,session_version FROM parent_accounts WHERE email=?",
                (invitation["email"],),
            ).fetchone()
            if account:
                if account["school_id"] != invitation["school_id"] or not account["active"] or not check_password_hash(account["password_hash"], request.form.get("current_password", "")):
                    db.rollback()
                    flash("The current parent password was not accepted.")
                    return redirect(url_for("parent_accept_invitation", token=token))
                parent_id = account["id"]
            else:
                password = request.form.get("password", "")
                confirm = request.form.get("confirm_password", "")
                if len(password) < 12 or len(password) > 256 or password != confirm:
                    db.rollback()
                    flash("Choose a matching password of 12 to 256 characters.")
                    return redirect(url_for("parent_accept_invitation", token=token))
                try:
                    cur = db.execute(
                        """INSERT INTO parent_accounts(school_id,email,password_hash,email_verified_at)
                           VALUES(?,?,?,?)""",
                        (invitation["school_id"], invitation["email"], generate_password_hash(password), now),
                    )
                    parent_id = cur.lastrowid
                except Exception:
                    db.rollback()
                    flash("Account activation could not be completed. Ask the school to issue a new invitation.")
                    return redirect(url_for("parent_login"))
            db.execute(
                """INSERT OR IGNORE INTO parent_student_links(parent_id,student_id,school_id)
                   VALUES(?,?,?)""",
                (parent_id, invitation["student_id"], invitation["school_id"]),
            )
            consumed = db.execute(
                "UPDATE parent_invitations SET used_at=? WHERE id=? AND used_at IS NULL AND expires_at>?",
                (now, invitation["id"], now),
            )
            if consumed.rowcount != 1:
                db.rollback()
                return parent_page("Invitation unavailable", "<h1>Invitation unavailable</h1><p class='error'>This invitation is invalid, expired, or already used. Ask the school to issue a new one.</p>"), 400
            account = db.execute(
                "SELECT id,school_id,session_version FROM parent_accounts WHERE id=?",
                (parent_id,),
            ).fetchone()
            db.commit()
        login_parent(account)
        flash("Parent account is ready. You can now view only the learner(s) linked to this account.")
        return redirect(url_for("parent_portal"))

    @app.route("/admin/parent-invitations", methods=["GET", "POST"])
    @admin_required
    def parent_invitations():
        if request.method == "POST":
            student_id = request.form.get("student_id", type=int)
            email = normalize_email(request.form.get("email"))
            if not student_id or len(email) > 254 or not EMAIL_RE.fullmatch(email):
                flash("Choose a learner and enter a valid parent email address.")
                return redirect(url_for("parent_invitations"))
            raw_token = secrets.token_urlsafe(32)
            expires = (datetime.now(timezone.utc) + timedelta(hours=24)).replace(microsecond=0).isoformat()
            with connect_db() as db:
                student = db.execute("SELECT id,school_id,full_name FROM students WHERE id=?", (student_id,)).fetchone()
                if not student:
                    flash("That learner could not be found.")
                    return redirect(url_for("parent_invitations"))
                db.execute(
                    """INSERT INTO parent_invitations(school_id,student_id,email,token_hash,expires_at,created_by)
                       VALUES(?,?,?,?,?,?)""",
                    (student["school_id"], student["id"], email, token_digest(raw_token), expires, str(session.get("admin_username", "admin"))),
                )
                db.commit()
            accept_url = url_for("parent_accept_invitation", token=raw_token, _external=True)
            body = (
                "You have been invited to create or extend a Scholar Tracker parent account.\n\n"
                f"Learner: {student['full_name']}\n"
                "This invitation expires in 24 hours and can be used only once.\n"
                "Open this secure link to continue:\n"
                f"{accept_url}\n\nIf you were not expecting this email, contact the school office."
            )
            if not send_email(email, "Your Scholar Tracker parent invitation", body):
                with connect_db() as db:
                    db.execute("UPDATE parent_invitations SET used_at=? WHERE token_hash=? AND used_at IS NULL", (utcnow(), token_digest(raw_token)))
                    db.commit()
                flash("Invitation email was not sent. Configure SMTP_HOST, SMTP_FROM and the mail credentials in Render before inviting parents.")
            else:
                flash("Invitation sent. The link expires in 24 hours and is stored only as a hash.")
            return redirect(url_for("parent_invitations"))
        with connect_db() as db:
            students = db.execute("SELECT id,full_name,class_name,stream FROM students ORDER BY class_name,stream,full_name").fetchall()
            invitations = db.execute(
                """SELECT i.email,i.expires_at,i.used_at,s.full_name,s.class_name,s.stream
                   FROM parent_invitations i JOIN students s ON s.id=i.student_id AND s.school_id=i.school_id
                   ORDER BY i.created_at DESC LIMIT 100"""
            ).fetchall()
        body = """
        <h1>Parent invitations</h1><p class="muted">Invitations are emailed to the supplied address, expire after 24 hours, and can be used once. Raw invitation tokens are never shown on this page.</p>
        <section class="panel"><h2>Invite a parent</h2><form method="post">
          {{ csrf_field() }}<div class="field"><label>Learner</label><select name="student_id" required>{% for s in students %}<option value="{{s.id}}">{{s.full_name}} — {{s.class_name}} / {{s.stream}}</option>{% endfor %}</select></div>
          <div class="field"><label>Parent email</label><input type="email" name="email" maxlength="254" required></div><button type="submit">Send invitation</button></form>
        </section><div class="table-wrap"><table><tr><th>Parent email</th><th>Learner</th><th>Expires</th><th>Status</th></tr>
        {% for i in invitations %}<tr><td>{{i.email}}</td><td>{{i.full_name}} — {{i.class_name}} / {{i.stream}}</td><td>{{i.expires_at}}</td><td>{{'Used' if i.used_at else 'Expired' if i.expires_at <= now else 'Pending / revoked if email failed'}}</td></tr>{% endfor %}</table></div>
        <div class="notice">Email delivery must be configured before use. No invitation URL is exposed in the admin page.</div>
        """
        return page("Parent invitations", body, students=students, invitations=invitations, now=utcnow())

    @app.route("/parents/forgot-password", methods=["GET", "POST"])
    @limiter.limit("5 per minute")
    def parent_forgot_password():
        if request.method == "POST":
            email = normalize_email(request.form.get("email"))
            if EMAIL_RE.fullmatch(email):
                with connect_db() as db:
                    account = db.execute("SELECT id,active FROM parent_accounts WHERE email=?", (email,)).fetchone()
                    if account and account["active"]:
                        now = utcnow()
                        db.execute("UPDATE parent_password_resets SET used_at=? WHERE parent_id=? AND used_at IS NULL", (now, account["id"]))
                        raw_token = secrets.token_urlsafe(32)
                        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0).isoformat()
                        db.execute(
                            "INSERT INTO parent_password_resets(parent_id,token_hash,expires_at) VALUES(?,?,?)",
                            (account["id"], token_digest(raw_token), expires),
                        )
                        db.commit()
                    else:
                        raw_token = None
                if raw_token:
                    reset_url = url_for("parent_reset_password", token=raw_token, _external=True)
                    delivered = send_email(
                        email,
                        "Reset your Scholar Tracker password",
                        "A password reset was requested for your Scholar Tracker account.\n"
                        "This link expires in one hour and can be used once:\n"
                        f"{reset_url}\n\nIf you did not request this, ignore this message.",
                    )
                    if not delivered:
                        with connect_db() as db:
                            db.execute("UPDATE parent_password_resets SET used_at=? WHERE token_hash=? AND used_at IS NULL", (utcnow(), token_digest(raw_token)))
                            db.commit()
            flash("If an active parent account matches that email and email delivery is available, password-reset instructions will be sent.")
            return redirect(url_for("parent_forgot_password"))
        body = """
        <h1>Reset parent password</h1><p class="muted">Enter your account email. The response is the same whether an account exists or not.</p>
        <section class="panel" style="max-width:560px"><form method="post">
          {{ csrf_field() }}<div class="field"><label>Email address</label><input type="email" name="email" maxlength="254" autocomplete="email" required></div>
          <button type="submit">Send reset instructions</button></form></section>
        """
        return parent_page("Reset parent password", body)

    @app.route("/parents/reset-password", methods=["GET", "POST"])
    @limiter.limit("10 per minute")
    def parent_reset_password():
        token = request.values.get("token", "")
        with connect_db() as db:
            row = db.execute(
                """SELECT r.id,r.parent_id,r.expires_at,p.school_id,p.active
                   FROM parent_password_resets r JOIN parent_accounts p ON p.id=r.parent_id
                   WHERE r.token_hash=? AND r.used_at IS NULL AND r.expires_at>?""",
                (token_digest(token), utcnow()),
            ).fetchone() if token and len(token) <= 200 else None
        if not row or not row["active"]:
            return parent_page("Reset link unavailable", "<h1>Reset link unavailable</h1><p class='error'>This link is invalid, expired, or already used. Request a new one.</p>"), 400
        if request.method == "GET":
            body = """
            <h1>Choose a new password</h1><section class="panel" style="max-width:600px"><form method="post">
              {{ csrf_field() }}<input type="hidden" name="token" value="{{ token }}">
              <div class="field"><label>New password (12 or more characters)</label><input type="password" name="password" minlength="12" maxlength="256" autocomplete="new-password" required></div>
              <div class="field"><label>Confirm new password</label><input type="password" name="confirm_password" minlength="12" maxlength="256" autocomplete="new-password" required></div>
              <button type="submit">Update password</button></form></section>
            """
            return parent_page("Choose a new password", body, token=token)
        password = request.form.get("password", "")
        if len(password) < 12 or len(password) > 256 or password != request.form.get("confirm_password", ""):
            flash("Choose a matching password of 12 to 256 characters.")
            return redirect(url_for("parent_reset_password", token=token))
        now = utcnow()
        with connect_db() as db:
            db.execute("BEGIN IMMEDIATE")
            reset = db.execute(
                """SELECT r.id,r.parent_id,p.active FROM parent_password_resets r
                   JOIN parent_accounts p ON p.id=r.parent_id
                   WHERE r.token_hash=? AND r.used_at IS NULL AND r.expires_at>?""",
                (token_digest(token), now),
            ).fetchone()
            if not reset or not reset["active"]:
                db.rollback()
                return parent_page("Reset link unavailable", "<h1>Reset link unavailable</h1><p class='error'>This link is invalid, expired, or already used. Request a new one.</p>"), 400
            db.execute(
                """UPDATE parent_accounts SET password_hash=?,password_changed_at=?,session_version=session_version+1
                   WHERE id=?""",
                (generate_password_hash(password), now, reset["parent_id"]),
            )
            db.execute("UPDATE parent_password_resets SET used_at=? WHERE parent_id=? AND used_at IS NULL", (now, reset["parent_id"]))
            db.commit()
        session.clear()
        flash("Password updated. Sign in using your new password.")
        return redirect(url_for("parent_login"))

    @app.route("/parents/portal")
    @parent_required
    def parent_portal():
        parent_id = session["parent_id"]
        school_id = session["parent_school_id"]
        end = date.today()
        start = (end - timedelta(days=29)).isoformat()
        end_text = end.isoformat()
        with connect_db() as db:
            children = db.execute(
                """SELECT s.id,s.full_name,s.class_name,s.stream,
                          COUNT(a.id) AS lessons,
                          SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) AS present,
                          SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) AS absent,
                          SUM(CASE WHEN a.status='Late' THEN 1 ELSE 0 END) AS late
                   FROM parent_student_links l
                   JOIN students s ON s.id=l.student_id AND s.school_id=l.school_id
                   LEFT JOIN attendance a ON a.student_id=s.id AND a.lesson_date BETWEEN ? AND ?
                   WHERE l.parent_id=? AND l.school_id=? AND l.revoked_at IS NULL
                     AND s.school_id=?
                   GROUP BY s.id,l.id
                   ORDER BY s.class_name,s.stream,s.full_name""",
                (start, end_text, parent_id, school_id, school_id),
            ).fetchall()
            events = db.execute(
                "SELECT event_date,title,details FROM events WHERE school_id=? AND event_date>=? ORDER BY event_date LIMIT 5",
                (school_id, end_text),
            ).fetchall()
            notices = db.execute(
                "SELECT title,body,created_at FROM school_notices WHERE school_id=? AND published=1 ORDER BY created_at DESC LIMIT 5",
                (school_id,),
            ).fetchall()
        body = """
        <h1>Family overview</h1><p class="muted">Attendance summaries cover the last 30 calendar days. Only children linked to this verified account are shown.</p>
        {% if children %}<div class="cards">{% for child in children %}<section class="panel">
          <h2>{{child.full_name}}</h2><p class="muted">{{child.class_name}} / {{child.stream}}</p>
          <div class="metric">{{child.present or 0}} / {{child.lessons or 0}}</div><p class="muted">Lessons present / marked</p>
          <p><strong>Absent:</strong> {{child.absent or 0}} &nbsp; <strong>Late:</strong> {{child.late or 0}}</p>
          <a class="btn" href="{{ url_for('parent_child_report',student_id=child.id) }}">View attendance report</a>
        </section>{% endfor %}</div>{% else %}<section class="panel"><p>No learner is linked to this account yet. Contact the school office if you expected to see a child.</p></section>{% endif %}
        <div class="cards"><section class="panel"><h2>School calendar</h2>{% if events %}{% for e in events %}<p><strong>{{e.event_date}}</strong> — {{e.title}}<br><span class="muted">{{e.details or ''}}</span></p>{% endfor %}{% else %}<p class="muted">No upcoming events have been published.</p>{% endif %}<a href="{{url_for('parent_calendar')}}">Open calendar</a></section>
        <section class="panel"><h2>School notices</h2>{% if notices %}{% for n in notices %}<p><strong>{{n.title}}</strong><br>{{n.body}}</p>{% endfor %}{% else %}<p class="muted">No notices have been published.</p>{% endif %}<a href="{{url_for('parent_notices')}}">All notices</a></section></div>
        """
        return parent_page("Family overview", body, children=children, events=events, notices=notices)

    @app.route("/parents/children/<int:student_id>/report")
    @parent_required
    def parent_child_report(student_id):
        parent_id = session["parent_id"]
        school_id = session["parent_school_id"]
        start = request.args.get("start", date.today().replace(day=1).isoformat())
        end = request.args.get("end", date.today().isoformat())
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            if start_date > end_date or (end_date - start_date).days > 366:
                raise ValueError
        except ValueError:
            abort(400, description="Choose a valid date range of up to one year.")
        with connect_db() as db:
            child = db.execute(
                """SELECT s.id,s.full_name,s.class_name,s.stream
                   FROM students s JOIN parent_student_links l
                     ON l.student_id=s.id AND l.school_id=s.school_id
                   WHERE s.id=? AND s.school_id=? AND l.parent_id=?
                     AND l.school_id=? AND l.revoked_at IS NULL""",
                (student_id, school_id, parent_id, school_id),
            ).fetchone()
            if not child:
                abort(404)
            rows = db.execute(
                """SELECT a.lesson_date,a.subject,a.status
                   FROM attendance a
                   JOIN students s ON s.id=a.student_id
                   JOIN parent_student_links l ON l.student_id=s.id AND l.school_id=s.school_id
                   WHERE s.id=? AND s.school_id=? AND l.parent_id=?
                     AND l.school_id=? AND l.revoked_at IS NULL
                     AND a.lesson_date BETWEEN ? AND ?
                   ORDER BY a.lesson_date DESC,a.subject""",
                (student_id, school_id, parent_id, school_id, start, end),
            ).fetchall()
        total = len(rows)
        present = sum(row["status"] == "Present" for row in rows)
        absent = sum(row["status"] == "Absent" for row in rows)
        late = sum(row["status"] == "Late" for row in rows)
        body = """
        <h1>Attendance report</h1><p class="muted">{{child.full_name}} · {{child.class_name}} / {{child.stream}}</p>
        <section class="panel"><form method="get"><div class="field"><label>From</label><input type="date" name="start" value="{{start}}" required></div><div class="field"><label>To</label><input type="date" name="end" value="{{end}}" required></div><button type="submit">Update report</button></form>
        <div class="cards"><div><span class="muted">Marked lessons</span><div class="metric">{{total}}</div></div><div><span class="muted">Present</span><div class="metric">{{present}}</div></div><div><span class="muted">Absent</span><div class="metric">{{absent}}</div></div><div><span class="muted">Late</span><div class="metric">{{late}}</div></div></div></section>
        <div class="table-wrap"><table><tr><th>Date</th><th>Subject</th><th>Status</th></tr>{% for r in rows %}<tr><td>{{r.lesson_date}}</td><td>{{r.subject}}</td><td>{{r.status}}</td></tr>{% endfor %}</table></div>
        <p class="muted">This report includes only saved lesson registers for the selected period. An unmarked lesson is not counted as an absence.</p>
        <a href="{{url_for('parent_portal')}}">Back to family overview</a>
        """
        return parent_page("Attendance report", body, child=child, rows=rows, start=start, end=end, total=total, present=present, absent=absent, late=late)

    @app.route("/parents/privacy")
    @parent_required
    def parent_privacy():
        parent_id = session["parent_id"]
        school_id = session["parent_school_id"]
        with connect_db() as db:
            account = db.execute("SELECT email,created_at,password_changed_at FROM parent_accounts WHERE id=? AND school_id=? AND active=1", (parent_id, school_id)).fetchone()
            children = db.execute(
                """SELECT s.id,s.full_name,s.class_name,s.stream
                   FROM parent_student_links l JOIN students s
                     ON s.id=l.student_id AND s.school_id=l.school_id
                   WHERE l.parent_id=? AND l.school_id=? AND l.revoked_at IS NULL
                   ORDER BY s.class_name,s.stream,s.full_name""",
                (parent_id, school_id),
            ).fetchall()
        body = """
        <h1>Privacy and account controls</h1><section class="panel"><h2>Verified account</h2><p><strong>Email:</strong> {{account.email}}</p><p><strong>Account created:</strong> {{account.created_at}}</p><p><strong>Password last changed:</strong> {{account.password_changed_at}}</p><a class="btn secondary" href="{{url_for('parent_forgot_password')}}">Reset password</a></section>
        <section class="panel"><h2>Children linked to this account</h2>{% if children %}<ul>{% for child in children %}<li>{{child.full_name}} — {{child.class_name}} / {{child.stream}}</li>{% endfor %}</ul>{% else %}<p>No active child links.</p>{% endif %}
        <p class="muted">Only the school can add or correct a child link. Contact the school office if any link is wrong. Log out on shared devices.</p>
        <form method="post" action="{{url_for('parent_logout')}}">{{csrf_field()}}<button type="submit">Log out of this device</button></form></section>
        """
        return parent_page("Privacy and account controls", body, account=account, children=children)

    @app.route("/parents/logout", methods=["POST"])
    def parent_logout():
        session.clear()
        flash("You have been logged out.")
        return redirect(url_for("parent_login"))

    def parent_calendar_secure():
        if session.get("role") != "parent":
            return redirect(url_for("parent_login", next=request.path))
        # parent_required validates account status and session version before rendering.
        return secure_calendar_view()

    @parent_required
    def secure_calendar_view():
        school_id = session["parent_school_id"]
        with connect_db() as db:
            events = db.execute(
                "SELECT event_date,title,details FROM events WHERE school_id=? ORDER BY event_date ASC",
                (school_id,),
            ).fetchall()
        body = """
        <h1>School calendar</h1><p class="muted">School-wide events for your linked school. This page does not show student records.</p>
        {% if events %}<div class="table-wrap"><table><tr><th>Date</th><th>Event</th><th>Details</th></tr>{% for e in events %}<tr><td>{{e.event_date}}</td><td>{{e.title}}</td><td>{{e.details or '—'}}</td></tr>{% endfor %}</table></div>{% else %}<section class="panel"><p>No school events have been published.</p></section>{% endif %}
        """
        return parent_page("School calendar", body, events=events)

    @parent_required
    def parent_notices_secure():
        school_id = session["parent_school_id"]
        with connect_db() as db:
            notices = db.execute(
                "SELECT title,body,created_at FROM school_notices WHERE school_id=? AND published=1 ORDER BY created_at DESC LIMIT 50",
                (school_id,),
            ).fetchall()
        body = """
        <h1>School notices</h1><p class="muted">Published announcements from your linked school.</p>
        {% if notices %}{% for n in notices %}<section class="panel"><h2>{{n.title}}</h2><p>{{n.body}}</p><p class="muted">{{n.created_at}}</p></section>{% endfor %}{% else %}<section class="panel"><p>No notices have been published.</p></section>{% endif %}
        """
        return parent_page("School notices", body, notices=notices)

    # Replace the older anonymous, school-global read-only views with the
    # authenticated, school-scoped versions while preserving their URLs.
    app.view_functions["parent_calendar"] = parent_calendar_secure
    app.view_functions["parent_notices"] = parent_notices_secure
