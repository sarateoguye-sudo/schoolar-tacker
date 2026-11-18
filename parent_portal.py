"""Secure parent portal routes for Scholar Tracker.

Parent-child links require school administrator approval. SMS/email delivery is
not claimed here; the portal displays records stored by the existing app.
"""
import re
import sqlite3
from datetime import date
from flask import Blueprint, request, redirect, url_for, render_template_string, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

def register_parent_portal(app, connect_db, csrf_field):
    bp = Blueprint("parent_portal", __name__)

    def init_parent_tables():
        with connect_db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS parent_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                phone TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS parent_student_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
                requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TEXT,
                UNIQUE(parent_id, student_id)
            );
            CREATE TABLE IF NOT EXISTS parent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER NOT NULL REFERENCES parent_users(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                reply TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Open' CHECK(status IN ('Open','Replied','Closed')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                replied_at TEXT
            );
            """)
            db.commit()

    def parent_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("role") != "parent" or not session.get("parent_id"):
                flash("Please sign in to the Parents' Portal.")
                return redirect(url_for("parent_portal.parent_login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    def parent_page(title, body, **context):
        body = re.sub(r'(<form\\b[^>]*method="post"[^>]*>)', r'\\1{{ csrf_field() }}', body, flags=re.I)
        shell = """
        <!doctype html><html lang="en"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>{{ title }} · Scholar Tracker</title>
        <style>
        :root{font-family:Inter,system-ui,Arial,sans-serif;color:#17243b;background:#f5f7fb}
        *{box-sizing:border-box}body{margin:0}header{background:#fff;border-bottom:1px solid #e5eaf2;padding:18px max(5vw,20px);display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
        header strong{font-size:1.1rem}nav{display:flex;gap:12px;flex-wrap:wrap}a{color:#4263eb;text-decoration:none;font-weight:650}
        main{max-width:1050px;margin:30px auto;padding:0 18px 40px}h1{letter-spacing:-.04em}h2{font-size:1.05rem}
        .muted{color:#738099}.panel,.card{background:white;border:1px solid #e5eaf2;border-radius:16px;padding:20px;margin:16px 0;box-shadow:0 8px 25px #1b2d5408}
        .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}.metric{font-size:1.8rem;font-weight:800;margin-top:8px}
        form{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:12px 0}.field{display:flex;flex-direction:column;gap:6px;min-width:200px;flex:1}
        label{font-size:.82rem;font-weight:750}input,textarea{font:inherit;border:1px solid #dce3ee;border-radius:9px;padding:11px;width:100%;background:#fff}
        button,.btn{border:0;border-radius:9px;padding:11px 15px;background:#4263eb;color:#fff;font:inherit;font-weight:750;cursor:pointer;display:inline-block}
        table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:12px;border-bottom:1px solid #e8ecf4;font-size:.9rem}th{background:#f8f9fc;font-size:.75rem;text-transform:uppercase;color:#738099}
        .table-wrap{overflow-x:auto;border:1px solid #e5eaf2;border-radius:12px;margin:14px 0}.notice{background:#eef3ff;border:1px solid #dce5ff;padding:13px;border-radius:10px;line-height:1.5}
        .flash{padding:12px;background:#e7f8f1;color:#087951;border-radius:10px;margin:10px 0}.pill{display:inline-block;background:#eef1ff;color:#405bd0;border-radius:20px;padding:4px 8px;font-size:.78rem;font-weight:700}
        </style></head><body><header><strong>🎓 Scholar Tracker <span class="muted">· Parents' Portal</span></strong>
        <nav><a href="{{ url_for('parent_portal.parent_dashboard') }}">Dashboard</a><a href="{{ url_for('parent_portal.parent_calendar') }}">School calendar</a><a href="{{ url_for('parent_portal.parent_messages') }}">Contact school</a>
        {% if signed_in %}<form method="post" action="{{ url_for('parent_portal.parent_logout') }}" style="margin:0"><button>Log out</button></form>{% else %}<a href="{{ url_for('parent_portal.parent_login') }}">Log in</a><a href="{{ url_for('parent_portal.parent_register') }}">Register</a>{% endif %}</nav></header>
        <main>{% for message in get_flashed_messages() %}<div class="flash">{{ message }}</div>{% endfor %}
        {{ body|safe }}</main></body></html>
        """
        return render_template_string(shell, title=title,
            body=render_template_string(body, csrf_field=csrf_field, **context),
            signed_in=session.get("role") == "parent", csrf_field=csrf_field)

    @bp.route("/parents")
    def parent_home():
        if session.get("role") == "parent":
            return redirect(url_for("parent_portal.parent_dashboard"))
        return redirect(url_for("parent_portal.parent_login"))

    @bp.route("/parents/register", methods=["GET", "POST"])
    def parent_register():
        if request.method == "POST":
            name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            password = request.form.get("password", "")
            if not name or not email or not phone or len(password) < 12:
                flash("Complete every field and use a password of at least 12 characters.")
            elif not re.fullmatch(r"[^@\\s]+@[^@\\s]+\\.[^@\\s]+", email):
                flash("Enter a valid email address.")
            else:
                try:
                    with connect_db() as db:
                        db.execute("INSERT INTO parent_users(full_name,email,phone,password_hash) VALUES(?,?,?,?)",
                                   (name, email, phone, generate_password_hash(password)))
                        db.commit()
                    flash("Parent account created. Sign in, then request a child link. The school must approve it before private records appear.")
                    return redirect(url_for("parent_portal.parent_login"))
                except sqlite3.IntegrityError:
                    flash("An account with that email already exists.")
        body = """
        <h1>Create a parent account</h1><p class="muted">Register with your own details. Your child's records remain hidden until the school approves the link request.</p>
        <section class="panel"><form method="post">
        <div class="field"><label>Full name</label><input name="full_name" autocomplete="name" required></div>
        <div class="field"><label>Email address</label><input type="email" name="email" autocomplete="email" required></div>
        <div class="field"><label>Phone number</label><input name="phone" autocomplete="tel" required></div>
        <div class="field"><label>Password (12+ characters)</label><input type="password" name="password" minlength="12" autocomplete="new-password" required></div>
        <button>Create account</button></form></section>"""
        return parent_page("Parent registration", body)

    @bp.route("/parents/login", methods=["GET", "POST"])
    def parent_login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            with connect_db() as db:
                user = db.execute("SELECT * FROM parent_users WHERE email=? AND active=1", (email,)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["role"] = "parent"
                session["parent_id"] = user["id"]
                session["parent_name"] = user["full_name"]
                session.permanent = True
                return redirect(url_for("parent_portal.parent_dashboard"))
            flash("Login failed. Check your email and password.")
        body = """
        <h1>Parent login</h1><p class="muted">Access attendance records, school dates and messages for children linked to your account.</p>
        <section class="panel" style="max-width:560px"><form method="post">
        <div class="field"><label>Email address</label><input type="email" name="email" autocomplete="username" required></div>
        <div class="field"><label>Password</label><input type="password" name="password" autocomplete="current-password" required></div><button>Sign in</button></form>
        <p>New here? <a href="{{ url_for('parent_portal.parent_register') }}">Create a parent account</a></p></section>"""
        return parent_page("Parent login", body)

    @bp.route("/parents/logout", methods=["POST"])
    @parent_required
    def parent_logout():
        session.clear()
        flash("You have been logged out.")
        return redirect(url_for("parent_portal.parent_login"))

    @bp.route("/parents/dashboard", methods=["GET", "POST"])
    @parent_required
    def parent_dashboard():
        parent_id = session["parent_id"]
        if request.method == "POST":
            admission = request.form.get("admission_no", "").strip()
            contact = request.form.get("parent_contact", "").strip()
            with connect_db() as db:
                student = db.execute("SELECT id FROM students WHERE admission_no=? AND parent_contact=?",
                                     (admission, contact)).fetchone()
                if not student:
                    flash("We couldn't match those details. Check with the school office if your contact details need updating.")
                else:
                    try:
                        db.execute("INSERT INTO parent_student_links(parent_id,student_id) VALUES(?,?)",
                                   (parent_id, student["id"]))
                        db.commit()
                        flash("Link request sent. Student records will remain hidden until the school approves it.")
                    except sqlite3.IntegrityError:
                        flash("You have already requested or linked this student.")
                    return redirect(url_for("parent_portal.parent_dashboard"))
        with connect_db() as db:
            links = db.execute("""SELECT l.id,l.status,s.id student_id,s.full_name,s.admission_no,s.class_name,s.stream
                FROM parent_student_links l JOIN students s ON s.id=l.student_id
                WHERE l.parent_id=? ORDER BY l.requested_at DESC""", (parent_id,)).fetchall()
            approved_ids = [r["student_id"] for r in links if r["status"] == "approved"]
            attendance = []
            if approved_ids:
                marks = ",".join("?" for _ in approved_ids)
                attendance = db.execute(f"""SELECT a.lesson_date,a.subject,a.status,a.marked_by,s.full_name,s.class_name
                    FROM attendance a JOIN students s ON s.id=a.student_id
                    WHERE a.student_id IN ({marks}) ORDER BY a.lesson_date DESC,a.id DESC LIMIT 100""",
                    approved_ids).fetchall()
            events = db.execute("SELECT event_date,title,details FROM events WHERE event_date>=? ORDER BY event_date LIMIT 5",
                                (date.today().isoformat(),)).fetchall()
            notices = db.execute("""SELECT n.created_at,n.message,n.status FROM notifications n
                JOIN parent_users p ON p.id=? WHERE n.recipient IN (p.phone,p.email)
                ORDER BY n.id DESC LIMIT 20""", (parent_id,)).fetchall()
        body = """
        <h1>Welcome, {{ name }}</h1><p class="muted">Your school updates and linked children's attendance.</p>
        <div class="grid"><div class="card"><span class="muted">Linked children</span><div class="metric">{{ approved_count }}</div></div>
        <div class="card"><span class="muted">Attendance records shown</span><div class="metric">{{ attendance|length }}</div></div>
        <div class="card"><span class="muted">Upcoming school events</span><div class="metric">{{ events|length }}</div></div></div>
        <section class="panel"><h2>Link a child</h2><p class="muted">Enter the admission number and the parent contact already recorded by the school. A school administrator must approve the request before records are visible.</p>
        <form method="post"><div class="field"><label>Student admission number</label><input name="admission_no" required></div><div class="field"><label>Parent contact on school record</label><input name="parent_contact" required></div><button>Request child link</button></form></section>
        <section class="panel"><h2>Children and link status</h2>{% if links %}<div class="table-wrap"><table><tr><th>Student</th><th>Class</th><th>Stream</th><th>Link status</th></tr>{% for s in links %}<tr><td>{{s.full_name}}</td><td>{{s.class_name}}</td><td>{{s.stream}}</td><td><span class="pill">{{s.status|title}}</span></td></tr>{% endfor %}</table></div>{% else %}<p>No child link requests yet.</p>{% endif %}</section>
        <section class="panel"><h2>Recent attendance</h2>{% if attendance %}<div class="table-wrap"><table><tr><th>Date</th><th>Student</th><th>Subject</th><th>Status</th></tr>{% for a in attendance %}<tr><td>{{a.lesson_date}}</td><td>{{a.full_name}}</td><td>{{a.subject}}</td><td><span class="pill">{{a.status}}</span></td></tr>{% endfor %}</table></div>{% else %}<p>No attendance records are available. If you requested a link, wait for the school to approve it.</p>{% endif %}</section>
        <div class="grid"><section class="panel"><h2>Upcoming calendar</h2>{% if events %}{% for e in events %}<p><strong>{{e.event_date}}</strong> — {{e.title}}<br><span class="muted">{{e.details or ''}}</span></p>{% endfor %}{% else %}<p>No upcoming events published.</p>{% endif %}<a href="{{url_for('parent_portal.parent_calendar')}}">View school calendar</a></section>
        <section class="panel"><h2>Notifications</h2>{% if notices %}{% for n in notices %}<p><strong>{{n.created_at}}</strong><br>{{n.message}}<br><span class="pill">{{n.status}}</span></p>{% endfor %}{% else %}<p>No notifications for your registered contact details yet.</p>{% endif %}</section></div>
        <p class="muted">SMS/email delivery is not enabled by this portal. The page displays records stored in Scholar Tracker only.</p>"""
        return parent_page("Parents' dashboard", body, name=session.get("parent_name","Parent"),
            links=links, approved_count=sum(1 for r in links if r["status"]=="approved"),
            attendance=attendance, events=events, notices=notices)

    @bp.route("/parents/calendar")
    def parent_calendar():
        with connect_db() as db:
            events = db.execute("SELECT event_date,title,details FROM events ORDER BY event_date").fetchall()
        body = """<h1>School calendar</h1><p class="muted">School events published by the administrator.</p>
        <section class="panel">{% if events %}<div class="table-wrap"><table><tr><th>Date</th><th>Event</th><th>Details</th></tr>
        {% for e in events %}<tr><td>{{e.event_date}}</td><td>{{e.title}}</td><td>{{e.details or '—'}}</td></tr>{% endfor %}</table></div>
        {% else %}<p>No school events have been published yet.</p>{% endif %}</section>"""
        return parent_page("School calendar", body, events=events)

    @bp.route("/parents/messages", methods=["GET", "POST"])
    @parent_required
    def parent_messages():
        parent_id = session["parent_id"]
        if request.method == "POST":
            subject = request.form.get("subject", "").strip()
            message = request.form.get("message", "").strip()
            if not subject or not message or len(subject) > 120 or len(message) > 3000:
                flash("Enter a subject and message (up to 3,000 characters).")
            else:
                with connect_db() as db:
                    db.execute("INSERT INTO parent_messages(parent_id,subject,message) VALUES(?,?,?)",
                               (parent_id, subject, message))
                    db.commit()
                flash("Your inquiry was sent to the school inbox.")
                return redirect(url_for("parent_portal.parent_messages"))
        with connect_db() as db:
            messages = db.execute("SELECT * FROM parent_messages WHERE parent_id=? ORDER BY id DESC", (parent_id,)).fetchall()
        body = """<h1>Contact the school</h1><p class="muted">Send an inquiry and review any reply from the school.</p>
        <section class="panel"><form method="post"><div class="field"><label>Subject</label><input name="subject" maxlength="120" required></div>
        <div class="field" style="flex-basis:100%"><label>Message</label><textarea name="message" rows="4" maxlength="3000" required></textarea></div><button>Send inquiry</button></form></section>
        <section class="panel"><h2>Your messages</h2>{% if messages %}{% for m in messages %}<article class="card"><strong>{{m.subject}}</strong> <span class="pill">{{m.status}}</span>
        <p>{{m.message}}</p>{% if m.reply %}<p><strong>School reply:</strong> {{m.reply}}</p>{% endif %}<small class="muted">{{m.created_at}}</small></article>{% endfor %}{% else %}<p>No messages yet.</p>{% endif %}</section>"""
        return parent_page("Contact school", body, messages=messages)

    @bp.route("/admin/parent-requests", methods=["GET", "POST"])
    def admin_parent_requests():
        if session.get("role") != "admin":
            abort(403)
        with connect_db() as db:
            if request.method == "POST":
                try:
                    link_id = int(request.form.get("link_id", ""))
                    action = request.form.get("action", "")
                    if action not in ("approved", "rejected"):
                        abort(400)
                    db.execute("UPDATE parent_student_links SET status=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
                               (action, link_id))
                    db.commit()
                    flash("Parent-child link request updated.")
                    return redirect(url_for("parent_portal.admin_parent_requests"))
                except ValueError:
                    abort(400)
            rows = db.execute("""SELECT l.id,l.status,l.requested_at,p.full_name parent_name,p.email,p.phone,
                s.full_name student_name,s.admission_no,s.class_name,s.stream
                FROM parent_student_links l JOIN parent_users p ON p.id=l.parent_id
                JOIN students s ON s.id=l.student_id ORDER BY CASE l.status WHEN 'pending' THEN 0 ELSE 1 END,l.id DESC""").fetchall()
        body = """<h1>Parent-child link requests</h1><p class="muted">Approve only after verifying the parent's identity and relationship to the student through your school's normal process.</p>
        <section class="panel">{% if rows %}<div class="table-wrap"><table><tr><th>Parent</th><th>Contact</th><th>Student</th><th>Requested</th><th>Status</th><th>Action</th></tr>
        {% for r in rows %}<tr><td>{{r.parent_name}}</td><td>{{r.email}}<br>{{r.phone}}</td><td>{{r.student_name}} ({{r.admission_no}})<br>{{r.class_name}} / {{r.stream}}</td><td>{{r.requested_at}}</td><td>{{r.status}}</td><td>{% if r.status=='pending' %}<form method="post" style="margin:0"><input type="hidden" name="link_id" value="{{r.id}}"><button name="action" value="approved">Approve</button><button name="action" value="rejected">Reject</button></form>{% else %}—{% endif %}</td></tr>{% endfor %}</table></div>{% else %}<p>No parent-child link requests.</p>{% endif %}</section>"""
        return parent_page("Parent link approvals", body, rows=rows)

    @bp.route("/admin/parent-messages", methods=["GET", "POST"])
    def admin_parent_messages():
        if session.get("role") != "admin":
            abort(403)
        with connect_db() as db:
            if request.method == "POST":
                try:
                    message_id = int(request.form.get("message_id", ""))
                except ValueError:
                    abort(400)
                reply = request.form.get("reply", "").strip()
                if not reply or len(reply) > 3000:
                    flash("Enter a reply up to 3,000 characters.")
                else:
                    db.execute("UPDATE parent_messages SET reply=?,status='Replied',replied_at=CURRENT_TIMESTAMP WHERE id=?",
                               (reply, message_id))
                    db.commit()
                    flash("Reply saved in the portal.")
                    return redirect(url_for("parent_portal.admin_parent_messages"))
            rows = db.execute("""SELECT m.*,p.full_name parent_name,p.email FROM parent_messages m
                JOIN parent_users p ON p.id=m.parent_id ORDER BY CASE m.status WHEN 'Open' THEN 0 ELSE 1 END,m.id DESC""").fetchall()
        body = """<h1>Parent inquiries</h1><p class="muted">Replies appear in the parent's portal; this does not send email or SMS.</p>
        {% if rows %}{% for m in rows %}<section class="panel"><strong>{{m.subject}}</strong> · {{m.parent_name}} ({{m.email}})<p>{{m.message}}</p>
        {% if m.reply %}<p><strong>Current reply:</strong> {{m.reply}}</p>{% endif %}<form method="post"><input type="hidden" name="message_id" value="{{m.id}}"><div class="field"><label>Reply</label><textarea name="reply" rows="3" maxlength="3000" required>{{m.reply}}</textarea></div><button>Save reply</button></form></section>{% endfor %}{% else %}<p>No parent inquiries yet.</p>{% endif %}"""
        return parent_page("Parent inquiries", body, rows=rows)

    app.register_blueprint(bp)
    init_parent_tables()
