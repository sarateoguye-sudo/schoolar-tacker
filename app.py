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
:root{--navy:#15294b;--blue:#3563e9;--blue2:#5b7cfa;--bg:#f5f7fc;--ink:#172338;--muted:#6b7890;--line:#e5eaf3;--mint:#e8faf3}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 90% 0%,#e8efff 0,transparent 28%),var(--bg);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;color:var(--ink)}
header{background:linear-gradient(115deg,#14284b,#234b86);color:white;padding:22px max(20px,calc((100% - 1180px)/2));display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;box-shadow:0 8px 24px #172b4b18}
header strong{font-size:1.25rem;letter-spacing:-.02em}header span{font-size:.85rem;color:#d4def0}
nav{background:#fff;padding:13px max(20px,calc((100% - 1180px)/2));display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--line);box-shadow:0 3px 12px #142b4a06}
a{color:var(--blue);text-decoration:none}nav a{font-weight:650;color:#40516d;font-size:.9rem;padding:9px 12px;border-radius:9px}nav a:hover{background:#edf2ff;color:var(--blue)}
main{max-width:1180px;margin:30px auto;padding:0 20px}.muted{color:var(--muted)}h1{font-size:clamp(1.6rem,3vw,2rem);letter-spacing:-.035em;margin:0 0 8px}h2{font-size:1.08rem;margin-top:0;letter-spacing:-.01em}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:22px 0}
.card,.panel{background:rgba(255,255,255,.94);border:1px solid var(--line);border-radius:17px;padding:21px;box-shadow:0 8px 24px #142b4a08}
.metric{font-size:2.15rem;font-weight:780;letter-spacing:-.04em;margin-top:10px;color:var(--navy)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:17px}
form{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:12px 0}label{display:block;font-size:.84rem;font-weight:700;margin-bottom:5px;color:#42516a}input,select,textarea{padding:10px 12px;border:1px solid #d5deec;border-radius:10px;background:white;font:inherit;max-width:100%;min-height:42px}
input:focus,select:focus,textarea:focus{outline:3px solid #dfe7ff;border-color:var(--blue)}.field{display:flex;flex-direction:column;gap:4px}button,.btn{background:linear-gradient(135deg,var(--blue),var(--blue2));color:white;border:0;border-radius:10px;padding:11px 15px;font:inherit;font-weight:700;cursor:pointer;display:inline-block;box-shadow:0 4px 10px #3563e922}button:hover,.btn:hover{filter:brightness(.97);transform:translateY(-1px)}
table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:13px 12px;border-bottom:1px solid var(--line);font-size:.91rem}th{color:var(--muted);font-size:.8rem;background:#f8faff;white-space:nowrap}tr:last-child td{border-bottom:0}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:13px;margin-top:14px}.notice{padding:13px 15px;background:#edf4ff;border:1px solid #dce8ff;border-radius:11px;margin:14px 0;color:#244b91}.flash{padding:13px 15px;background:var(--mint);color:#096b4c;border-radius:10px;margin:10px 0}.pill{padding:5px 9px;border-radius:20px;background:#eef2ff;color:#354d9c;font-size:.8rem;font-weight:650}
footer{text-align:center;color:var(--muted);padding:32px 20px;font-size:.85rem}
</style></head><body>
<header><div><strong>🎓 Scholar Tracker</strong><br><span>School attendance and communication</span></div><span>Prototype · Sample data</span></header>
<nav><a href="{{ url_for('dashboard') }}">Dashboard</a><a href="{{ url_for('students_page') }}">Students</a><a href="{{ url_for('attendance_page') }}">Lesson attendance</a><a href="{{ url_for('timetable_page') }}">Teachers timetable</a><a href="{{ url_for('reports') }}">Reports</a><a href="{{ url_for('calendar_page') }}">School calendar</a><a href="{{ url_for('notifications_page') }}">Parent notifications</a></nav>
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

@app.route("/timetable", methods=["GET", "POST"])
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
