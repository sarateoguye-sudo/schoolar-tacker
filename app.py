import os
import sqlite3
from datetime import date
from flask import Flask, request, redirect, url_for, render_template_string, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-before-deployment")
DB_PATH = os.environ.get("SCHOLAR_DB", "scholar_tracker.db")

def connect_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
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
        """)
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
<title>{{ title }} · Scholar Tracker</title>
<style>
:root{--navy:#142b4a;--blue:#2463eb;--bg:#f4f7fb;--ink:#172338;--muted:#66758a;--line:#e2e8f0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:Inter,Arial,sans-serif;color:var(--ink)}
header{background:var(--navy);color:white;padding:18px max(20px,calc((100% - 1120px)/2));display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
header strong{font-size:1.2rem}header span{font-size:.85rem;color:#cbd5e1}
nav{background:#fff;padding:12px max(20px,calc((100% - 1120px)/2));display:flex;gap:18px;flex-wrap:wrap;border-bottom:1px solid var(--line)}
a{color:var(--blue);text-decoration:none}nav a{font-weight:600;color:var(--navy);font-size:.93rem}
main{max-width:1120px;margin:28px auto;padding:0 20px}.muted{color:var(--muted)}h1{font-size:1.8rem;margin:0 0 8px}h2{font-size:1.1rem;margin-top:0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:22px 0}
.card,.panel{background:white;border:1px solid var(--line);border-radius:14px;padding:20px;box-shadow:0 3px 12px #142b4a08}
.metric{font-size:2rem;font-weight:750;margin-top:10px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px}
form{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin:12px 0}label{display:block;font-size:.86rem;font-weight:650;margin-bottom:5px}input,select,textarea{padding:10px 11px;border:1px solid #cbd5e1;border-radius:8px;background:white;font:inherit;max-width:100%}
.field{display:flex;flex-direction:column;gap:4px}button,.btn{background:var(--blue);color:white;border:0;border-radius:8px;padding:10px 14px;font:inherit;font-weight:650;cursor:pointer;display:inline-block}
table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line);font-size:.92rem}th{color:var(--muted);font-size:.82rem;background:#f8fafc}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;margin-top:14px}.notice{padding:12px 14px;background:#eff6ff;border-radius:9px;margin:14px 0;color:#1e40af}.flash{padding:12px;background:#ecfdf5;color:#065f46;border-radius:8px;margin:10px 0}.pill{padding:4px 8px;border-radius:20px;background:#eef2ff;font-size:.8rem}
footer{text-align:center;color:var(--muted);padding:30px;font-size:.85rem}
</style></head><body>
<header><div><strong>🎓 Scholar Tracker</strong><br><span>School attendance and communication</span></div><span>Prototype · Sample data</span></header>
<nav><a href="{{ url_for('dashboard') }}">Dashboard</a><a href="{{ url_for('students_page') }}">Students</a><a href="{{ url_for('attendance_page') }}">Lesson attendance</a><a href="{{ url_for('reports') }}">Reports</a><a href="{{ url_for('calendar_page') }}">School calendar</a><a href="{{ url_for('notifications_page') }}">Parent notifications</a></nav>
<main>
{% for message in get_flashed_messages() %}<div class="flash">{{ message }}</div>{% endfor %}
{{ body|safe }}
</main><footer>Scholar Tracker · Built as a learning prototype for school attendance management.</footer></body></html>
"""

def page(title, body, **context):
    return render_template_string(PAGE, title=title, body=render_template_string(body, **context))

@app.route("/")
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

@app.route("/reports")
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

@app.route("/notifications")
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

init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
