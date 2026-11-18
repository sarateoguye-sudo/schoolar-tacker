"""Teacher-specific attendance assignments and scoped class registers."""
from datetime import date
import sqlite3
from functools import wraps
from flask import request, redirect, url_for, render_template_string, flash, session, abort

def register_teacher_assignments(app, connect_db, csrf_field):
    with connect_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS teacher_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_user_id INTEGER NOT NULL REFERENCES teacher_users(id) ON DELETE CASCADE,
            subject TEXT NOT NULL, class_name TEXT NOT NULL, stream TEXT NOT NULL DEFAULT 'A',
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(teacher_user_id, subject, class_name, stream))""")
        db.commit()

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
            if session.get("role") != "teacher" or not session.get("teacher_user_id"):
                return redirect(url_for("teacher_login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    def render(title, body, **ctx):
        body = body.replace('<form method="post">', '<form method="post">{{ csrf_field() }}')
        shell = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>{{title}} · Scholar Tracker</title><style>
        body{margin:0;background:#f5f7fb;color:#17243b;font:15px system-ui,Arial}header{background:#fff;border-bottom:1px solid #e4e9f2;padding:18px 5%;display:flex;gap:18px;flex-wrap:wrap;justify-content:space-between}
        main{max-width:1100px;margin:28px auto;padding:0 18px}h1{letter-spacing:-.04em}.muted{color:#718099}.panel{background:#fff;border:1px solid #e4e9f2;border-radius:15px;padding:20px;margin:16px 0}
        form{display:flex;flex-wrap:wrap;gap:12px;align-items:end}label{display:block;font-size:.82rem;font-weight:700;margin-bottom:5px}input,select{padding:10px;border:1px solid #d5ddea;border-radius:8px;font:inherit}
        button,.btn{display:inline-block;border:0;border-radius:8px;background:#4263eb;color:#fff;padding:10px 14px;font:inherit;font-weight:700;text-decoration:none;cursor:pointer}
        table{border-collapse:collapse;width:100%;min-width:540px}th,td{text-align:left;padding:11px;border-bottom:1px solid #e7ebf2}th{background:#f8f9fc;font-size:.78rem}.table-wrap{overflow:auto;border:1px solid #e7ebf2;border-radius:10px;margin-top:12px}
        .flash{background:#e7f8f1;padding:12px;border-radius:9px;margin:10px 0}nav{display:flex;gap:12px;flex-wrap:wrap}nav a{color:#4263eb;text-decoration:none}
        </style></head><body><header><strong>🎓 Scholar Tracker</strong><nav><a href="{{url_for('dashboard')}}">Admin dashboard</a> <a href="{{url_for('admin_teachers')}}">Teacher accounts</a> <a href="{{url_for('teacher_portal')}}">Teacher portal</a></nav></header>
        <main>{% for message in get_flashed_messages() %}<div class="flash">{{message}}</div>{% endfor %}{{body|safe}}</main></body></html>"""
        return render_template_string(shell, title=title, body=render_template_string(body, csrf_field=csrf_field, **ctx), csrf_field=csrf_field)

    @app.route("/admin/teacher-assignments", methods=["GET", "POST"])
    @admin_required
    def admin_teacher_assignments():
        with connect_db() as db:
            if request.method == "POST":
                if request.form.get("action") == "toggle":
                    try:
                        aid = int(request.form.get("assignment_id", ""))
                    except ValueError:
                        abort(400)
                    db.execute("UPDATE teacher_assignments SET active=1-active WHERE id=?", (aid,))
                    db.commit()
                    flash("Assignment status updated.")
                    return redirect(url_for("admin_teacher_assignments"))
                try:
                    tid = int(request.form.get("teacher_user_id", ""))
                except ValueError:
                    tid = 0
                subject = request.form.get("subject", "").strip()
                cls = request.form.get("class_name", "").strip()
                stream = request.form.get("stream", "A").strip() or "A"
                valid_teacher = db.execute("SELECT id FROM teacher_users WHERE id=? AND active=1 AND username!='teacher'", (tid,)).fetchone()
                if not valid_teacher or not subject or not cls or len(subject)>100 or len(cls)>100 or len(stream)>30:
                    flash("Select an active named teacher and enter a valid subject, class and stream.")
                else:
                    try:
                        db.execute("INSERT INTO teacher_assignments(teacher_user_id,subject,class_name,stream) VALUES(?,?,?,?)", (tid,subject,cls,stream))
                        db.commit()
                        flash("Teacher assignment saved.")
                        return redirect(url_for("admin_teacher_assignments"))
                    except sqlite3.IntegrityError:
                        flash("That exact assignment already exists for this teacher.")
            teachers = db.execute("SELECT id,username,teacher_name FROM teacher_users WHERE active=1 AND username!='teacher' ORDER BY teacher_name").fetchall()
            assignments = db.execute("""SELECT a.id,a.subject,a.class_name,a.stream,a.active,t.teacher_name,t.username
                FROM teacher_assignments a JOIN teacher_users t ON t.id=a.teacher_user_id ORDER BY t.teacher_name,a.class_name,a.stream,a.subject""").fetchall()
        body = """<h1>Teacher class and subject assignments</h1><p class="muted">Assign each teacher only the subjects, classes and streams they are authorised to teach.</p>
        <section class="panel"><h2>Create assignment</h2>{% if teachers %}<form method="post"><div><label>Teacher account</label><select name="teacher_user_id" required>{% for t in teachers %}<option value="{{t.id}}">{{t.teacher_name}} · {{t.username}}</option>{% endfor %}</select></div>
        <div><label>Subject</label><input name="subject" maxlength="100" placeholder="Mathematics" required></div><div><label>Class</label><input name="class_name" maxlength="100" placeholder="Form 2" required></div>
        <div><label>Stream</label><input name="stream" maxlength="30" value="A" required></div><button>Save assignment</button></form>{% else %}<p>Create a named teacher account first in <a href="{{url_for('admin_teachers')}}">Teacher accounts</a>.</p>{% endif %}</section>
        <section class="panel"><h2>Current assignments</h2>{% if assignments %}<div class="table-wrap"><table><tr><th>Teacher</th><th>Subject</th><th>Class</th><th>Stream</th><th>Status</th><th>Action</th></tr>
        {% for a in assignments %}<tr><td>{{a.teacher_name}} ({{a.username}})</td><td>{{a.subject}}</td><td>{{a.class_name}}</td><td>{{a.stream}}</td><td>{{'Active' if a.active else 'Disabled'}}</td><td><form method="post"><input type="hidden" name="action" value="toggle"><input type="hidden" name="assignment_id" value="{{a.id}}"><button>{{'Disable' if a.active else 'Activate'}}</button></form></td></tr>{% endfor %}</table></div>{% else %}<p>No assignments created yet.</p>{% endif %}</section>"""
        return render("Teacher assignments", body, teachers=teachers, assignments=assignments)

    @app.route("/teacher/assigned-registers")
    @teacher_required
    def assigned_registers():
        with connect_db() as db:
            rows = db.execute("SELECT id,subject,class_name,stream FROM teacher_assignments WHERE teacher_user_id=? AND active=1 ORDER BY class_name,stream,subject", (session["teacher_user_id"],)).fetchall()
        body = """<h1>My assigned classes</h1><p class="muted">Only classes, streams and subjects assigned by the school administrator are shown.</p>
        {% if rows %}<section class="panel"><div class="table-wrap"><table><tr><th>Subject</th><th>Class</th><th>Stream</th><th>Register</th></tr>{% for a in rows %}<tr><td>{{a.subject}}</td><td>{{a.class_name}}</td><td>{{a.stream}}</td><td><a class="btn" href="{{url_for('assigned_register',assignment_id=a.id)}}">Open register</a></td></tr>{% endfor %}</table></div></section>{% else %}<section class="panel"><p>No active assignments yet. Contact the school administrator.</p></section>{% endif %}"""
        return render("My assigned classes", body, rows=rows)

    @app.route("/teacher/assigned-registers/<int:assignment_id>", methods=["GET", "POST"])
    @teacher_required
    def assigned_register(assignment_id):
        chosen_date = request.values.get("lesson_date", date.today().isoformat())
        try:
            date.fromisoformat(chosen_date)
        except ValueError:
            chosen_date = date.today().isoformat()
        with connect_db() as db:
            assignment = db.execute("SELECT id,subject,class_name,stream FROM teacher_assignments WHERE id=? AND teacher_user_id=? AND active=1",
                                    (assignment_id, session["teacher_user_id"])).fetchone()
            if not assignment:
                abort(403, description="This class assignment is not available to your account.")
            students = db.execute("SELECT id,admission_no,full_name FROM students WHERE class_name=? AND stream=? ORDER BY full_name",
                                  (assignment["class_name"], assignment["stream"])).fetchall()
            if request.method == "POST":
                for student in students:
                    status = request.form.get("status_"+str(student["id"]), "Present")
                    if status not in ("Present","Absent","Late"):
                        abort(400, description="Invalid attendance status.")
                    db.execute("""INSERT INTO attendance(student_id,lesson_date,subject,status,marked_by) VALUES(?,?,?,?,?)
                        ON CONFLICT(student_id,lesson_date,subject) DO UPDATE SET status=excluded.status,marked_by=excluded.marked_by""",
                        (student["id"],chosen_date,assignment["subject"],status,session.get("teacher_name","Teacher")))
                    if status == "Absent":
                        contact = db.execute("SELECT parent_contact,full_name FROM students WHERE id=?", (student["id"],)).fetchone()
                        if contact and contact["parent_contact"]:
                            db.execute("INSERT INTO notifications(recipient,message,status) VALUES(?,?,?)",
                                (contact["parent_contact"], f"Demo alert: {contact['full_name']} was marked absent for {assignment['subject']} on {chosen_date}.", "Demo only — not sent"))
                db.commit()
                flash("Register saved for your assigned class. Alerts are stored in-app only; no messages were sent.")
                return redirect(url_for("assigned_register", assignment_id=assignment_id, lesson_date=chosen_date))
            saved = db.execute("""SELECT a.student_id,a.status FROM attendance a JOIN students s ON s.id=a.student_id
                WHERE a.lesson_date=? AND a.subject=? AND s.class_name=? AND s.stream=?""",
                (chosen_date,assignment["subject"],assignment["class_name"],assignment["stream"])).fetchall()
            saved_map = {r["student_id"]:r["status"] for r in saved}
        body = """<h1>Class register</h1><p class="muted">{{assignment.subject}} · {{assignment.class_name}} / {{assignment.stream}}</p>
        <section class="panel"><form method="get"><div><label>Attendance date</label><input type="date" name="lesson_date" value="{{chosen_date}}" required></div><button>Load date</button></form></section>
        {% if students %}<section class="panel"><form method="post"><input type="hidden" name="lesson_date" value="{{chosen_date}}"><div class="table-wrap"><table><tr><th>Admission number</th><th>Student</th><th>Status</th></tr>
        {% for s in students %}<tr><td>{{s.admission_no}}</td><td>{{s.full_name}}</td><td><select name="status_{{s.id}}">{% for status in ['Present','Absent','Late'] %}<option {% if saved_map.get(s.id,'Present')==status %}selected{% endif %}>{{status}}</option>{% endfor %}</select></td></tr>{% endfor %}</table></div><button>Save register</button></form></section>
        {% else %}<section class="panel"><p>No students found in this class and stream. Ask the administrator to check the class/stream names.</p></section>{% endif %}
        <p><a class="btn" href="{{url_for('assigned_registers')}}">Back to my assignments</a></p>"""
        return render("Class register", body, assignment=assignment, chosen_date=chosen_date, students=students, saved_map=saved_map)
