"""Online-only resilience features for Scholar Tracker.

This module adds an attendance follow-up dashboard, unmarked-register queue,
published notices, and tightly scoped champion tasks. It intentionally does not
cache records or provide offline attendance.
"""
from datetime import date, timedelta
from flask import request, redirect, url_for, flash, session, abort
import sqlite3


def init_resilience_db(connect_db):
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS school_notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            published INTEGER NOT NULL DEFAULT 0,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS champion_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id),
            champion_name TEXT NOT NULL,
            task_summary TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open' CHECK(status IN ('Open','In progress','Completed','Cancelled')),
            due_date TEXT DEFAULT '',
            completion_note TEXT DEFAULT '',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_role TEXT NOT NULL,
            actor_id TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            target_type TEXT NOT NULL DEFAULT '',
            target_id TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL DEFAULT 'success',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Upgrade existing SQLite databases safely without destructive migration.
        cols = {row["name"] for row in db.execute("PRAGMA table_info(attendance)").fetchall()}
        if "reason_code" not in cols:
            db.execute("ALTER TABLE attendance ADD COLUMN reason_code TEXT NOT NULL DEFAULT 'Unknown'")
        db.commit()


def register_resilience_routes(app, connect_db, admin_required, teacher_required, page):
    def audit(action, target_type="", target_id="", outcome="success"):
        role = str(session.get("role", "anonymous"))
        actor_id = str(session.get("admin_username") or session.get("teacher_user_id") or "")
        with connect_db() as db:
            db.execute(
                "INSERT INTO audit_events(actor_role,actor_id,action,target_type,target_id,outcome) VALUES(?,?,?,?,?,?)",
                (role, actor_id, action, target_type, str(target_id), outcome),
            )
            db.commit()

    @app.route("/attendance-risk")
    @admin_required
    def attendance_risk():
        end = request.args.get("end", date.today().isoformat())
        try:
            end_date = date.fromisoformat(end)
        except ValueError:
            end_date = date.today()
            end = end_date.isoformat()
        start = (end_date - timedelta(days=45)).isoformat()
        class_filter = request.args.get("class_name", "")
        with connect_db() as db:
            classes = [r["class_name"] for r in db.execute("SELECT DISTINCT class_name FROM students ORDER BY class_name")]
            sql = """SELECT s.id,s.full_name,s.admission_no,s.class_name,s.stream,
                     a.lesson_date,a.subject,a.status
                     FROM students s LEFT JOIN attendance a
                     ON a.student_id=s.id AND a.lesson_date BETWEEN ? AND ?"""
            params = [start, end]
            if class_filter:
                sql += " WHERE s.class_name=?"
                params.append(class_filter)
            sql += " ORDER BY s.class_name,s.stream,s.full_name,a.lesson_date DESC,a.id DESC"
            rows = db.execute(sql, params).fetchall()
        grouped = {}
        for row in rows:
            item = grouped.setdefault(row["id"], {
                "name": row["full_name"], "admission": row["admission_no"],
                "class_name": row["class_name"], "stream": row["stream"],
                "records": [], "absent": 0, "late": 0, "streak": 0
            })
            if row["lesson_date"]:
                item["records"].append(row["status"])
        result = []
        for item in grouped.values():
            recent = item["records"][:10]
            item["absent"] = sum(s == "Absent" for s in recent)
            item["late"] = sum(s == "Late" for s in recent)
            for status in recent:
                if status == "Absent":
                    item["streak"] += 1
                else:
                    break
            denominator = len(recent)
            absent_rate = (item["absent"] / denominator) if denominator else 0
            if item["streak"] >= 3 or (denominator >= 5 and absent_rate >= 0.4):
                item["level"] = "Red — needs prompt follow-up"
            elif item["absent"] >= 2 or item["late"] >= 3:
                item["level"] = "Yellow — check in"
            else:
                item["level"] = "Green — no current warning"
            item["reason"] = (
                f"{item['streak']} consecutive recorded absences" if item["streak"] >= 3
                else f"{item['absent']} absences and {item['late']} late arrivals in the latest {denominator} records"
            )
            result.append(item)
        result.sort(key=lambda x: (0 if x["level"].startswith("Red") else 1 if x["level"].startswith("Yellow") else 2, x["class_name"], x["name"]))
        body = """
        <h1>Attendance follow-up</h1>
        <p class="muted">Supportive indicators based on recorded attendance only. They are prompts for staff review, not diagnoses or predictions.</p>
        <section class="panel"><form method="get"><div class="field"><label>Class</label><select name="class_name"><option value="">All classes</option>{% for c in classes %}<option {% if c==class_filter %}selected{% endif %}>{{c}}</option>{% endfor %}</select></div><div class="field"><label>As at</label><input type="date" name="end" value="{{end}}"></div><button>Filter</button></form></section>
        <div class="table-wrap"><table><tr><th>Learner</th><th>Class / stream</th><th>Recent absences</th><th>Late</th><th>Follow-up level</th><th>Reason</th></tr>
        {% for s in students %}<tr><td>{{s.name}}</td><td>{{s.class_name}} / {{s.stream}}</td><td>{{s.absent}}</td><td>{{s.late}}</td><td>{{s.level}}</td><td>{{s.reason}}</td></tr>{% endfor %}</table></div>
        <p class="muted">Missing registers are excluded from these counts; review the unmarked-register queue separately.</p>
        """
        return page("Attendance follow-up", body, students=result, classes=classes, class_filter=class_filter, end=end)

    @app.route("/unmarked-registers")
    @admin_required
    def unmarked_registers():
        chosen_date = request.args.get("date", date.today().isoformat())
        try:
            date.fromisoformat(chosen_date)
        except ValueError:
            chosen_date = date.today().isoformat()
        weekday = date.fromisoformat(chosen_date).strftime("%A")
        with connect_db() as db:
            lessons = db.execute(
                "SELECT * FROM teacher_timetable WHERE weekday=? ORDER BY start_time,teacher_name",
                (weekday,),
            ).fetchall()
            queue = []
            for lesson in lessons:
                expected = db.execute(
                    "SELECT COUNT(*) FROM students WHERE class_name=? AND stream=?",
                    (lesson["class_name"], lesson["stream"]),
                ).fetchone()[0]
                marked = db.execute(
                    """SELECT COUNT(DISTINCT a.student_id) FROM attendance a
                       JOIN students s ON s.id=a.student_id
                       WHERE a.lesson_date=? AND a.subject=? AND s.class_name=? AND s.stream=?""",
                    (chosen_date, lesson["subject"], lesson["class_name"], lesson["stream"]),
                ).fetchone()[0]
                if expected == 0 or marked < expected:
                    queue.append({
                        "teacher": lesson["teacher_name"], "time": lesson["start_time"],
                        "subject": lesson["subject"], "class_name": lesson["class_name"],
                        "stream": lesson["stream"], "expected": expected, "marked": marked,
                        "missing": max(expected-marked, 0)
                    })
        body = """
        <h1>Unmarked-register queue</h1><p class="muted">This compares the timetable with saved attendance. It flags incomplete registers; it does not assume an unmarked learner is absent.</p>
        <section class="panel"><form method="get"><div class="field"><label>School date</label><input type="date" name="date" value="{{chosen_date}}" required></div><button>Check registers</button></form></section>
        {% if queue %}<div class="table-wrap"><table><tr><th>Lesson</th><th>Teacher</th><th>Class / stream</th><th>Marked / expected</th><th>Unmarked count</th></tr>{% for r in queue %}<tr><td>{{r.time}} · {{r.subject}}</td><td>{{r.teacher}}</td><td>{{r.class_name}} / {{r.stream}}</td><td>{{r.marked}} / {{r.expected}}</td><td>{{r.missing}}</td></tr>{% endfor %}</table></div>{% else %}<section class="panel"><p>No incomplete registers were found for this date based on the current timetable.</p></section>{% endif %}
        """
        return page("Unmarked registers", body, queue=queue, chosen_date=chosen_date)

    @app.route("/notices", methods=["GET", "POST"])
    @admin_required
    def school_notices():
        with connect_db() as db:
            if request.method == "POST":
                title = request.form.get("title", "").strip()
                body_text = request.form.get("body", "").strip()
                published = 1 if request.form.get("published") == "on" else 0
                if not title or not body_text:
                    flash("A title and notice text are required.")
                else:
                    cur = db.execute(
                        "INSERT INTO school_notices(title,body,published,created_by) VALUES(?,?,?,?)",
                        (title, body_text, published, str(session.get("admin_username", "admin"))),
                    )
                    db.commit()
                    audit("notice_created", "school_notice", cur.lastrowid)
                    flash("Notice saved.")
                    return redirect(url_for("school_notices"))
            notices = db.execute("SELECT * FROM school_notices ORDER BY created_at DESC LIMIT 100").fetchall()
        body = """
        <h1>School notices</h1><p class="muted">Publish school-wide information. Do not include private learner or family information.</p>
        <section class="panel"><h2>Create notice</h2><form method="post" style="align-items:stretch"><div class="field"><label>Title</label><input name="title" required maxlength="160"></div><div class="field" style="flex:1;min-width:240px"><label>Notice</label><textarea name="body" rows="3" required maxlength="3000"></textarea></div><label><input type="checkbox" name="published"> Publish to parent notice page</label><button type="submit">Save notice</button></form></section>
        <div class="table-wrap"><table><tr><th>Created</th><th>Title</th><th>Visibility</th><th>Notice</th></tr>{% for n in notices %}<tr><td>{{n.created_at}}</td><td>{{n.title}}</td><td>{{'Published' if n.published else 'Draft'}}</td><td>{{n.body}}</td></tr>{% endfor %}</table></div>
        """
        return page("School notices", body, notices=notices)

    @app.route("/parents/notices")
    def parent_notices():
        with connect_db() as db:
            notices = db.execute(
                "SELECT title,body,created_at FROM school_notices WHERE published=1 ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
        body = """
        <h1>School notices</h1><p class="muted">Published announcements from the school.</p>
        {% if notices %}{% for n in notices %}<section class="panel"><h2>{{n.title}}</h2><p>{{n.body}}</p><p class="muted">{{n.created_at}}</p></section>{% endfor %}{% else %}<section class="panel"><p>No notices have been published.</p></section>{% endif %}
        <p class="muted">This page contains public school announcements only. Student-specific information requires a secure parent account, which is not yet implemented.</p>
        """
        return page("School notices for parents", body, notices=notices)

    @app.route("/champion-tasks", methods=["GET", "POST"])
    @admin_required
    def champion_tasks():
        with connect_db() as db:
            if request.method == "POST":
                student_id = request.form.get("student_id", type=int)
                champion_name = request.form.get("champion_name", "").strip()
                task_summary = request.form.get("task_summary", "").strip()
                due_date = request.form.get("due_date", "").strip()
                student = db.execute("SELECT id FROM students WHERE id=?", (student_id,)).fetchone() if student_id else None
                if not student or not champion_name or not task_summary:
                    flash("Select a learner and enter an approved champion name and minimum-necessary task summary.")
                elif len(task_summary) > 240:
                    flash("Keep the task summary under 240 characters and exclude sensitive family details.")
                else:
                    cur = db.execute(
                        """INSERT INTO champion_tasks(student_id,champion_name,task_summary,due_date,created_by)
                           VALUES(?,?,?,?,?)""",
                        (student_id, champion_name, task_summary, due_date, str(session.get("admin_username", "admin"))),
                    )
                    db.commit()
                    audit("champion_task_created", "champion_task", cur.lastrowid)
                    flash("Private follow-up task created. Champion self-service login is not enabled yet.")
                    return redirect(url_for("champion_tasks"))
            students = db.execute("SELECT id,full_name,class_name,stream FROM students ORDER BY class_name,stream,full_name").fetchall()
            tasks = db.execute(
                """SELECT t.*,s.full_name,s.class_name,s.stream FROM champion_tasks t
                   JOIN students s ON s.id=t.student_id ORDER BY t.created_at DESC LIMIT 100"""
            ).fetchall()
        body = """
        <h1>Attendance Champion tasks</h1><p class="muted">Administrator-only task assignment. Do not put sensitive reasons, marks, discipline records, or family details in the task summary.</p>
        <section class="panel"><h2>Assign follow-up</h2><form method="post"><div class="field"><label>Learner</label><select name="student_id" required>{% for s in students %}<option value="{{s.id}}">{{s.full_name}} — {{s.class_name}} / {{s.stream}}</option>{% endfor %}</select></div><div class="field"><label>Approved champion name</label><input name="champion_name" required maxlength="120"></div><div class="field"><label>Minimum-necessary task summary</label><input name="task_summary" required maxlength="240" value="Please make a respectful welfare follow-up"></div><div class="field"><label>Due date</label><input type="date" name="due_date"></div><button type="submit">Create task</button></form></section>
        <div class="table-wrap"><table><tr><th>Learner</th><th>Class</th><th>Champion</th><th>Task</th><th>Status</th><th>Due</th></tr>{% for t in tasks %}<tr><td>{{t.full_name}}</td><td>{{t.class_name}} / {{t.stream}}</td><td>{{t.champion_name}}</td><td>{{t.task_summary}}</td><td>{{t.status}}</td><td>{{t.due_date or '—'}}</td></tr>{% endfor %}</table></div>
        <div class="notice">Champion accounts and restricted self-service access are not enabled in this phase; only administrators can view these tasks.</div>
        """
        return page("Attendance Champion tasks", body, students=students, tasks=tasks)

    @app.route("/audit-log")
    @admin_required
    def audit_log():
        with connect_db() as db:
            rows = db.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT 200").fetchall()
        body = """
        <h1>Audit log</h1><p class="muted">Security-relevant actions recorded by this resilience module. This is not yet a complete audit trail for all attendance edits.</p>
        <div class="table-wrap"><table><tr><th>Time</th><th>Actor role</th><th>Actor ID</th><th>Action</th><th>Target</th><th>Outcome</th></tr>{% for r in rows %}<tr><td>{{r.created_at}}</td><td>{{r.actor_role}}</td><td>{{r.actor_id}}</td><td>{{r.action}}</td><td>{{r.target_type}} {{r.target_id}}</td><td>{{r.outcome}}</td></tr>{% endfor %}</table></div>
        """
        return page("Audit log", body, rows=rows)
