import os, sqlite3, secrets, hmac, io, csv
from datetime import date, datetime
from zoneinfo import ZoneInfo
from functools import wraps
from flask import Flask, request, redirect, url_for, render_template_string, flash, session, abort, make_response
from werkzeug.security import generate_password_hash, check_password_hash

app=Flask(__name__); app.secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32)
DB=os.environ.get("SCHOLAR_DB","scholar_tracker.db")
ROLES=("admin","teacher","parent")

def conn():
 d=sqlite3.connect(DB); d.row_factory=sqlite3.Row; d.execute("PRAGMA foreign_keys=ON"); return d
def init():
 with conn() as d:
  d.executescript("""
  CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,full_name TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('admin','teacher','parent')),active INTEGER NOT NULL DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY,admission_no TEXT UNIQUE NOT NULL,full_name TEXT NOT NULL,class_name TEXT NOT NULL,stream TEXT NOT NULL DEFAULT 'A',parent_contact TEXT DEFAULT '',parent_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,active INTEGER NOT NULL DEFAULT 1);
  CREATE TABLE IF NOT EXISTS teacher_assignments(id INTEGER PRIMARY KEY,teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,class_name TEXT NOT NULL,subject TEXT NOT NULL,UNIQUE(teacher_id,class_name,subject));
  CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY,student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,lesson_date TEXT NOT NULL,subject TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('Present','Absent','Late')),marked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(student_id,lesson_date,subject));
  CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,event_date TEXT NOT NULL,title TEXT NOT NULL,details TEXT DEFAULT '',created_by INTEGER REFERENCES users(id) ON DELETE SET NULL);
  CREATE TABLE IF NOT EXISTS timetable(id INTEGER PRIMARY KEY,weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),start_time TEXT NOT NULL,end_time TEXT NOT NULL,class_name TEXT NOT NULL,subject TEXT NOT NULL,room TEXT DEFAULT '',teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE);
  CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,created_at TEXT DEFAULT CURRENT_TIMESTAMP,recipient_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,message TEXT NOT NULL,read_at TEXT);
  CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY,actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,action TEXT NOT NULL,details TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(lesson_date);
  """)
  # Add columns to older prototype databases without dropping records.
  for table, col, decl in [("students","parent_user_id","INTEGER REFERENCES users(id)"),("students","active","INTEGER NOT NULL DEFAULT 1"),("attendance","marked_by","INTEGER REFERENCES users(id)"),("attendance","updated_at","TEXT DEFAULT CURRENT_TIMESTAMP"),("notifications","recipient_user_id","INTEGER REFERENCES users(id)"),("notifications","student_id","INTEGER REFERENCES students(id)"),("notifications","read_at","TEXT")]:
   cols={x["name"] for x in d.execute("PRAGMA table_info("+table+")")}
   if col not in cols: d.execute("ALTER TABLE "+table+" ADD COLUMN "+col+" "+decl)
  if not d.execute("SELECT COUNT(*) FROM students").fetchone()[0]:
   d.executemany("INSERT INTO students(admission_no,full_name,class_name,stream) VALUES(?,?,?,?)",[("DEMO001","Amina Sample","Form 1","A"),("DEMO002","Brian Sample","Form 1","A"),("DEMO003","Chao Sample","Form 1","B"),("DEMO004","David Sample","Form 2","A")])
def who():
 if not session.get("uid"): return None
 with conn() as d: return d.execute("SELECT id,username,full_name,role,active FROM users WHERE id=?",(session["uid"],)).fetchone()
def log(action,detail=""):
 if session.get("uid"):
  with conn() as d: d.execute("INSERT INTO audit_log(actor_id,action,details) VALUES(?,?,?)",(session["uid"],action,detail[:300]))
def login_required(f):
 @wraps(f)
 def w(*a,**k):
  if not who(): return redirect(url_for("login",next=request.path))
  return f(*a,**k)
 return w
def roles(*allowed):
 def dec(f):
  @wraps(f)
  @login_required
  def w(*a,**k):
   u=who()
   if not u or u["role"] not in allowed: abort(403)
   return f(*a,**k)
  return w
 return dec
@app.before_request
def guard():
 if request.method=="POST":
  t=session.get("csrf","")
  if not t or not request.form.get("_csrf") or not hmac.compare_digest(t,request.form.get("_csrf")): abort(400)
 u=who()
 if u and not u["active"]: session.clear(); flash("Account disabled. Contact the administrator."); return redirect(url_for("login"))
@app.context_processor
def globals_():
 if not session.get("csrf"): session["csrf"]=secrets.token_urlsafe(32)
 u=who(); unread_count=0
 if u and u["role"] in ("parent","teacher"):
  with conn() as d: unread_count=d.execute("SELECT COUNT(*) FROM notifications WHERE recipient_user_id=? AND read_at IS NULL",(u["id"],)).fetchone()[0]
 return {"csrf":session["csrf"],"viewer":u,"unread_count":unread_count}
@app.after_request
def headers(r):
 r.headers["X-Content-Type-Options"]="nosniff"; r.headers["X-Frame-Options"]="DENY"; r.headers["Referrer-Policy"]="strict-origin-when-cross-origin"; r.headers["Cache-Control"]="no-store"; r.headers["Content-Security-Policy"]="default-src 'self' 'unsafe-inline'; frame-ancestors 'none'"; return r

SHELL="""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>{{title}} · Scholar Tracker</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f6fb;color:#172338;font:15px Arial}header{background:#142b4a;color:white;padding:18px max(18px,calc((100% - 1120px)/2));display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}nav{background:white;padding:13px max(18px,calc((100% - 1120px)/2));display:flex;gap:15px;flex-wrap:wrap;border-bottom:1px solid #dfe6f0}nav a{color:#142b4a;font-weight:bold}a{color:#245eea;text-decoration:none}main{max-width:1120px;margin:25px auto;padding:0 18px}h1{font-size:1.8rem}h2{font-size:1.1rem}.muted{color:#66758a}.badge{display:inline-block;background:#dc2626;color:white;border-radius:999px;padding:2px 7px;font-size:12px;margin-left:4px}.panel,.card{background:white;border:1px solid #dfe6f0;border-radius:12px;padding:18px;margin:14px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px}.metric{font-size:2rem;font-weight:bold;margin-top:8px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}form{display:flex;flex-wrap:wrap;align-items:end;gap:10px;margin:12px 0}.field{display:flex;flex-direction:column;gap:5px}label{font-weight:bold;font-size:.86rem}input,select{padding:10px;border:1px solid #cbd5e1;border-radius:7px;font:inherit;max-width:100%}button,.btn{background:#245eea;color:white;border:0;border-radius:7px;padding:10px 13px;font-weight:bold;cursor:pointer;display:inline-block}.secondary{background:#e8eef8;color:#142b4a}.table-wrap{overflow:auto;border:1px solid #dfe6f0;border-radius:10px;margin:14px 0}table{border-collapse:collapse;width:100%;background:white}td,th{text-align:left;padding:10px;border-bottom:1px solid #e2e8f0;white-space:normal}th{background:#f8fafc;color:#66758a}.flash,.notice{padding:12px;border-radius:8px;background:#ecfdf5;color:#065f46;margin:12px 0}.notice{background:#eff6ff;color:#1e40af}.auth{max-width:460px;margin:40px auto}.auth input{width:100%}.auth form{display:grid}footer{text-align:center;color:#66758a;padding:25px}</style></head><body><header><div><b>🎓 Scholar Tracker</b><br><small>School attendance and communication</small></div><div>{% if viewer %}{{viewer.full_name}} · {{viewer.role}} · <a style='color:white' href='{{url_for("logout")}}'>Sign out</a>{% else %}Local prototype{% endif %}</div></header>
{% if viewer %}<nav><a href='{{url_for("home")}}'>Dashboard</a>{% if viewer.role in ['admin','teacher'] %}<a href='{{url_for("attendance")}}'>Lesson attendance</a><a href='{{url_for("reports")}}'>Reports</a>{% endif %}{% if viewer.role=="admin" %}<a href='{{url_for("students")}}'>Students</a><a href='{{url_for("accounts")}}'>Accounts</a><a href='{{url_for("assignments")}}'>Teacher assignments</a>{% endif %}<a href='{{url_for("calendar")}}'>School calendar</a><a href='{{url_for("timetable")}}'>Timetable</a><a href='{{url_for("notifications")}}'>🔔 Notifications{% if unread_count %}<span class=badge>{{unread_count}}</span>{% endif %}</a>{% if viewer.role=="parent" %}<a href='{{url_for("parent")}}'>My children</a>{% endif %}</nav>{% endif %}
<main>{% for m in get_flashed_messages() %}<div class=flash>{{m}}</div>{% endfor %}{{body|safe}}</main><footer>Scholar Tracker · Development prototype · Not published</footer></body></html>"""
def page(title,body,**kw): return render_template_string(SHELL,title=title,body=render_template_string(body,**kw))

@app.route("/setup",methods=["GET","POST"])
def setup():
 with conn() as d: exists=d.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
 if exists: return redirect(url_for("login"))
 if request.method=="POST":
  required=os.environ.get("SETUP_TOKEN",""); given=request.form.get("setup_token","")
  if required and not hmac.compare_digest(required,given): flash("Invalid setup token.")
  else:
   name=request.form.get("full_name","").strip(); username=request.form.get("username","").strip(); pw=request.form.get("password","")
   if len(name)<2 or len(username)<3 or len(pw)<12: flash("Name, username (3+ characters), and password (12+ characters) are required.")
   else:
    with conn() as d: d.execute("INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,'admin')",(username,generate_password_hash(pw),name))
    flash("Administrator created. Please sign in."); return redirect(url_for("login"))
 body="""<div class=auth><section class=panel><h1>Initial setup</h1><p class=muted>Create the first administrator. Configure SETUP_TOKEN on any shared server.</p><form method=post><input type=hidden name=_csrf value='{{csrf}}'><div class=field><label>Setup token (if configured)</label><input name=setup_token></div><div class=field><label>Full name</label><input name=full_name required></div><div class=field><label>Username</label><input name=username minlength=3 required></div><div class=field><label>Password (12+ characters)</label><input type=password name=password minlength=12 required></div><button>Create administrator</button></form></section></div>"""
 return page("Initial setup",body)
@app.route("/login",methods=["GET","POST"])
def login():
 with conn() as d: n=d.execute("SELECT COUNT(*) FROM users").fetchone()[0]
 if not n: return redirect(url_for("setup"))
 if request.method=="POST":
  with conn() as d: u=d.execute("SELECT * FROM users WHERE username=? AND active=1",(request.form.get("username","").strip(),)).fetchone()
  if u and check_password_hash(u["password_hash"],request.form.get("password","")):
   session.clear(); session["uid"]=u["id"]; session["csrf"]=secrets.token_urlsafe(32); log("login")
   nxt=request.args.get("next","")
   return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("home"))
  flash("Invalid username or password.")
 body="""<div class=auth><section class=panel><h1>Sign in</h1><form method=post><input type=hidden name=_csrf value='{{csrf}}'><div class=field><label>Username</label><input name=username required autocomplete=username></div><div class=field><label>Password</label><input type=password name=password required autocomplete=current-password></div><button>Sign in</button></form></section></div>"""
 return page("Sign in",body)
@app.route("/logout")
@login_required
def logout(): log("logout"); session.clear(); flash("Signed out."); return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
 u=who(); today=date.today().isoformat()
 with conn() as d:
  if u["role"]=="parent":
   kids=d.execute("SELECT * FROM students WHERE parent_user_id=? AND active=1",(u["id"],)).fetchall(); ids=[x["id"] for x in kids]
   marks=d.execute("SELECT a.*,s.full_name FROM attendance a JOIN students s ON s.id=a.student_id WHERE s.parent_user_id=? ORDER BY a.lesson_date DESC,a.id DESC LIMIT 10",(u["id"],)).fetchall()
   unread=d.execute("SELECT COUNT(*) FROM notifications WHERE recipient_user_id=? AND read_at IS NULL",(u["id"],)).fetchone()[0]
   body="""<h1>Parent dashboard</h1><div class=cards><div class=card>Linked children<div class=metric>{{kids|length}}</div></div><div class=card>Unread alerts<div class=metric>{{unread}}</div></div></div><section class=panel><h2>Recent attendance</h2>{% for a in marks %}<p>{{a.lesson_date}} · {{a.full_name}} · {{a.subject}} · <b>{{a.status}}</b></p>{% else %}<p class=muted>No attendance yet.</p>{% endfor %}<a class=btn href='{{url_for("parent")}}'>View children</a></section>"""
   return page("Dashboard",body,kids=kids,marks=marks,unread=unread)
  if u["role"]=="teacher":
   classes=[x["class_name"] for x in d.execute("SELECT DISTINCT class_name FROM teacher_assignments WHERE teacher_id=?",(u["id"],)).fetchall()]
   now=datetime.now(ZoneInfo("Africa/Nairobi")); today=now.date().isoformat(); weekday=now.weekday(); clock=now.strftime("%H:%M")
   lessons=d.execute("SELECT * FROM timetable WHERE teacher_id=? AND weekday=? ORDER BY start_time",(u["id"],weekday)).fetchall()
   current_lesson=next((x for x in lessons if x["start_time"]<=clock<x["end_time"]),None)
   students=0; stats={}
   if classes:
    q=",".join("?"*len(classes)); students=d.execute("SELECT COUNT(*) FROM students WHERE active=1 AND class_name IN ("+q+")",classes).fetchone()[0]
    stats={x["status"]:x["n"] for x in d.execute("SELECT status,COUNT(*) n FROM attendance a JOIN students s ON s.id=a.student_id WHERE lesson_date=? AND s.class_name IN ("+q+") GROUP BY status",[today]+classes).fetchall()}
   if current_lesson:
    msg=f"Lesson in progress: {current_lesson['subject']} for {current_lesson['class_name']} ({current_lesson['start_time']}-{current_lesson['end_time']})."
    exists=d.execute("SELECT 1 FROM notifications WHERE recipient_user_id=? AND message=? AND created_at LIKE ?",(u["id"],msg,today+"%")).fetchone()
    if not exists:
     ncols={x["name"] for x in d.execute("PRAGMA table_info(notifications)")}
     if "recipient" in ncols: d.execute("INSERT INTO notifications(recipient,recipient_user_id,message) VALUES(?,?,?)",(u["username"],u["id"],msg))
     else: d.execute("INSERT INTO notifications(recipient_user_id,message) VALUES(?,?)",(u["id"],msg))
     d.commit()
   body="""<h1>Teacher dashboard</h1><p class=muted>Your assigned classes and lesson schedule.</p><div class=cards><div class=card>Assigned classes<div class=metric>{{classes|length}}</div></div><div class=card>Assigned students<div class=metric>{{students}}</div></div><div class=card>Present today<div class=metric>{{stats.get('Present',0)}}</div></div><div class=card>Absent today<div class=metric>{{stats.get('Absent',0)}}</div></div></div>{% if current_lesson %}<section class=panel><h2>🔔 Lesson happening now</h2><p><b>{{current_lesson.subject}}</b> · {{current_lesson.class_name}} · {{current_lesson.start_time}}–{{current_lesson.end_time}}</p><p>Room: {{current_lesson.room or 'Not set'}}</p><a class=btn href='{{url_for("attendance",class_name=current_lesson.class_name,subject=current_lesson.subject)}}'>Mark this lesson's attendance</a></section>{% else %}<p class=notice>No lesson is scheduled for you right now. Your timetable is shown below.</p>{% endif %}<section class=panel><h2>Today's lessons</h2>{% for lesson in lessons %}<p>{{lesson.start_time}}–{{lesson.end_time}} · {{lesson.subject}} · {{lesson.class_name}} · {{lesson.room or 'Room not set'}}</p>{% else %}<p class=muted>No lessons scheduled for today. Ask the administrator to set the timetable.</p>{% endfor %}</section><p class=notice>Ask the administrator to assign your classes and subjects if none appear.</p><a class=btn href='{{url_for("attendance")}}'>Mark attendance</a>"""
   return page("Teacher dashboard",body,classes=classes,students=students,stats=stats,lessons=lessons,current_lesson=current_lesson)
  students=d.execute("SELECT COUNT(*) FROM students WHERE active=1").fetchone()[0]; classes=d.execute("SELECT COUNT(DISTINCT class_name) FROM students WHERE active=1").fetchone()[0]
  stats={x["status"]:x["n"] for x in d.execute("SELECT status,COUNT(*) n FROM attendance WHERE lesson_date=? GROUP BY status",(today,)).fetchall()}
  recent=d.execute("SELECT a.*,s.full_name FROM attendance a JOIN students s ON s.id=a.student_id ORDER BY a.lesson_date DESC,a.id DESC LIMIT 8").fetchall()
  events=d.execute("SELECT * FROM events WHERE event_date>=? ORDER BY event_date LIMIT 5",(today,)).fetchall()
 body="""<h1>School overview</h1><div class=cards><div class=card>Active students<div class=metric>{{students}}</div></div><div class=card>Classes<div class=metric>{{classes}}</div></div><div class=card>Present today<div class=metric>{{stats.get('Present',0)}}</div></div><div class=card>Absent today<div class=metric>{{stats.get('Absent',0)}}</div></div><div class=card>Late today<div class=metric>{{stats.get('Late',0)}}</div></div></div><div class=grid><section class=panel><h2>Recent attendance</h2>{% for a in recent %}<p>{{a.lesson_date}} · {{a.full_name}} · {{a.subject}} · {{a.status}}</p>{% else %}<p class=muted>No records yet.</p>{% endfor %}</section><section class=panel><h2>Upcoming events</h2>{% for e in events %}<p>{{e.event_date}} · {{e.title}} — {{e.details}}</p>{% else %}<p class=muted>No events.</p>{% endfor %}<a class=btn href='{{url_for("calendar")}}'>Calendar</a></section></div>"""
 return page("Dashboard",body,students=students,classes=classes,stats=stats,recent=recent,events=events)

@app.route("/students",methods=["GET","POST"])
@roles("admin")
def students():
 with conn() as d:
  parents=d.execute("SELECT id,full_name,username FROM users WHERE role='parent' AND active=1 ORDER BY full_name").fetchall()
  if request.method=="POST":
   vals=[request.form.get(k,"").strip() for k in ("admission_no","full_name","class_name")]; stream=request.form.get("stream","A").strip() or "A"; contact=request.form.get("parent_contact","").strip(); puid=request.form.get("parent_user_id") or None
   if not all(vals): flash("Admission number, full name and class are required.")
   else:
    try:
     d.execute("INSERT INTO students(admission_no,full_name,class_name,stream,parent_contact,parent_user_id) VALUES(?,?,?,?,?,?)",(*vals,stream,contact,puid)); d.commit(); log("student_added",vals[0]); flash("Student added."); return redirect(url_for("students"))
    except sqlite3.IntegrityError: flash("Admission number already exists.")
  rows=d.execute("SELECT s.*,u.full_name parent_name FROM students s LEFT JOIN users u ON u.id=s.parent_user_id ORDER BY s.active DESC,s.class_name,s.stream,s.full_name").fetchall()
 body="""<h1>Student register</h1><section class=panel><h2>Add student</h2><form method=post><input type=hidden name=_csrf value='{{csrf}}'><div class=field><label>Admission number</label><input name=admission_no required></div><div class=field><label>Full name</label><input name=full_name required></div><div class=field><label>Class</label><input name=class_name placeholder='Form 1' required></div><div class=field><label>Stream</label><input name=stream value=A></div><div class=field><label>Parent contact (optional)</label><input name=parent_contact></div><div class=field><label>Parent account</label><select name=parent_user_id><option value=''>Not linked</option>{% for p in parents %}<option value={{p.id}}>{{p.full_name}} ({{p.username}})</option>{% endfor %}</select></div><button>Add student</button></form></section><div class=table-wrap><table><tr><th>Admission</th><th>Name</th><th>Class/stream</th><th>Parent</th><th>Status</th><th></th></tr>{% for s in rows %}<tr><td>{{s.admission_no}}</td><td>{{s.full_name}}</td><td>{{s.class_name}} / {{s.stream}}</td><td>{{s.parent_name or 'Not linked'}}</td><td>{{'Active' if s.active else 'Archived'}}</td><td>{% if s.active %}<form method=post action='{{url_for("archive",sid=s.id)}}'><input type=hidden name=_csrf value='{{csrf}}'><button class=secondary>Archive</button></form>{% endif %}</td></tr>{% endfor %}</table></div>"""
 return page("Students",body,parents=parents,rows=rows)
@app.route("/students/<int:sid>/archive",methods=["POST"])
@roles("admin")
def archive(sid):
 with conn() as d: d.execute("UPDATE students SET active=0 WHERE id=?",(sid,))
 log("student_archived",str(sid)); flash("Student archived; history retained."); return redirect(url_for("students"))

@app.route("/accounts",methods=["GET","POST"])
@roles("admin")
def accounts():
 with conn() as d:
  if request.method=="POST":
   name=request.form.get("full_name","").strip(); username=request.form.get("username","").strip(); role=request.form.get("role",""); pw=request.form.get("password","")
   if len(name)<2 or len(username)<3 or role not in ROLES or len(pw)<12: flash("Enter a name, username (3+ chars), role, and password (12+ chars).")
   else:
    try:
     d.execute("INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)",(username,generate_password_hash(pw),name,role)); d.commit(); log("account_created",username+":"+role); flash("Account created."); return redirect(url_for("accounts"))
    except sqlite3.IntegrityError: flash("Username already exists.")
  users=d.execute("SELECT id,username,full_name,role,active FROM users ORDER BY role,full_name").fetchall()
 body="""<h1>User accounts</h1><section class=panel><h2>Create teacher or parent account</h2><form method=post><input type=hidden name=_csrf value='{{csrf}}'><div class=field><label>Full name</label><input name=full_name required></div><div class=field><label>Username</label><input name=username minlength=3 required></div><div class=field><label>Role</label><select name=role><option value=teacher>Teacher</option><option value=parent>Parent</option><option value=admin>Administrator</option></select></div><div class=field><label>Password (12+ characters)</label><input type=password name=password minlength=12 required></div><button>Create account</button></form></section><div class=table-wrap><table><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th>Action</th></tr>{% for u in users %}<tr><td>{{u.full_name}}</td><td>{{u.username}}</td><td>{{u.role}}</td><td>{{'Active' if u.active else 'Disabled'}}</td><td>{% if u.id!=viewer.id %}<form method=post action='{{url_for("toggle",uid=u.id)}}'><input type=hidden name=_csrf value='{{csrf}}'><button class=secondary>{{'Disable' if u.active else 'Enable'}}</button></form>{% else %}Current account{% endif %}</td></tr>{% endfor %}</table></div>"""
 return page("Accounts",body,users=users)
@app.route("/accounts/<int:uid>/toggle",methods=["POST"])
@roles("admin")
def toggle(uid):
 with conn() as d:
  u=d.execute("SELECT role,active FROM users WHERE id=?",(uid,)).fetchone()
  if not u: abort(404)
  if u["role"]=="admin" and u["active"] and d.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]<2: flash("Cannot disable the last active administrator."); return redirect(url_for("accounts"))
  d.execute("UPDATE users SET active=? WHERE id=?",(0 if u["active"] else 1,uid))
 log("account_toggled",str(uid)); flash("Account updated."); return redirect(url_for("accounts"))

@app.route("/assignments",methods=["GET","POST"])
@roles("admin")
def assignments():
 with conn() as d:
  teachers=d.execute("SELECT id,full_name,username FROM users WHERE role='teacher' AND active=1 ORDER BY full_name").fetchall()
  if request.method=="POST":
   tid=request.form.get("teacher_id"); cls=request.form.get("class_name","").strip(); sub=request.form.get("subject","").strip()
   if not tid or not cls or not sub: flash("Teacher, class and subject are required.")
   else:
    try: d.execute("INSERT INTO teacher_assignments(teacher_id,class_name,subject) VALUES(?,?,?)",(tid,cls,sub)); d.commit(); flash("Assignment saved."); return redirect(url_for("assignments"))
    except sqlite3.IntegrityError: flash("Assignment already exists.")
  rows=d.execute("SELECT a.*,u.full_name FROM teacher_assignments a JOIN users u ON u.id=a.teacher_id ORDER BY a.class_name,a.subject").fetchall()
 body="""<h1>Teacher assignments</h1><p class=muted>Teachers can mark attendance only for assigned classes and subjects.</p><section class=panel><form method=post><input type=hidden name=_csrf value='{{csrf}}'><div class=field><label>Teacher</label><select name=teacher_id required>{% for t in teachers %}<option value={{t.id}}>{{t.full_name}} ({{t.username}})</option>{% endfor %}</select></div><div class=field><label>Class</label><input name=class_name placeholder='Form 1' required></div><div class=field><label>Subject</label><input name=subject placeholder=Mathematics required></div><button>Assign teacher</button></form></section><div class=table-wrap><table><tr><th>Teacher</th><th>Class</th><th>Subject</th><th></th></tr>{% for a in rows %}<tr><td>{{a.full_name}}</td><td>{{a.class_name}}</td><td>{{a.subject}}</td><td><form method=post action='{{url_for("del_assignment",aid=a.id)}}'><input type=hidden name=_csrf value='{{csrf}}'><button class=secondary>Remove</button></form></td></tr>{% endfor %}</table></div>"""
 return page("Assignments",body,teachers=teachers,rows=rows)
@app.route("/assignments/<int:aid>/delete",methods=["POST"])
@roles("admin")
def del_assignment(aid):
 with conn() as d: d.execute("DELETE FROM teacher_assignments WHERE id=?",(aid,))
 flash("Assignment removed."); return redirect(url_for("assignments"))

@app.route("/attendance",methods=["GET","POST"])
@roles("admin","teacher")
def attendance():
 u=who(); day=request.values.get("lesson_date",date.today().isoformat()); cls=request.values.get("class_name",""); sub=request.values.get("subject","").strip()
 with conn() as d:
  if u["role"]=="admin":
   classes=[r["class_name"] for r in d.execute("SELECT DISTINCT class_name FROM students WHERE active=1 ORDER BY class_name")]
   assigns=d.execute("SELECT class_name,subject FROM teacher_assignments ORDER BY class_name,subject").fetchall()
  else:
   assigns=d.execute("SELECT class_name,subject FROM teacher_assignments WHERE teacher_id=?",(u["id"],)).fetchall(); classes=sorted(set(r["class_name"] for r in assigns))
  if not cls and classes: cls=classes[0]
  if u["role"]=="teacher" and cls not in classes: abort(403)
  subs=sorted(set(r["subject"] for r in assigns if r["class_name"]==cls))
  if not sub and subs: sub=subs[0]
  if u["role"]=="teacher" and not any(r["class_name"]==cls and r["subject"]==sub for r in assigns): abort(403)
  if u["role"]=="admin" and not sub: sub="General"
  if request.method=="POST":
   if u["role"]=="teacher" and not any(r["class_name"]==cls and r["subject"]==sub for r in assigns): abort(403)
   students=d.execute("SELECT * FROM students WHERE class_name=? AND active=1",(cls,)).fetchall()
   for s in students:
    status=request.form.get("s"+str(s["id"]),"Absent")
    if status not in ("Present","Absent","Late"): status="Absent"
    d.execute("""INSERT INTO attendance(student_id,lesson_date,subject,status,marked_by) VALUES(?,?,?,?,?) ON CONFLICT(student_id,lesson_date,subject) DO UPDATE SET status=excluded.status,marked_by=excluded.marked_by,updated_at=CURRENT_TIMESTAMP""",(s["id"],day,sub,status,u["id"]))
    if status=="Absent" and s["parent_user_id"]:
     msg=f"Attendance alert: {s['full_name']} was marked absent for {sub} on {day}."
     if not d.execute("SELECT 1 FROM notifications WHERE recipient_user_id=? AND student_id=? AND message=?",(s["parent_user_id"],s["id"],msg)).fetchone():
      ncols={x["name"] for x in d.execute("PRAGMA table_info(notifications)")}
      if "recipient" in ncols:
       d.execute("INSERT INTO notifications(recipient,recipient_user_id,student_id,message) VALUES(?,?,?,?)",(s["parent_contact"] or "",s["parent_user_id"],s["id"],msg))
      else:
       d.execute("INSERT INTO notifications(recipient_user_id,student_id,message) VALUES(?,?,?)",(s["parent_user_id"],s["id"],msg))
   d.commit(); log("attendance_saved",cls+"/"+sub+"/"+day); flash("Attendance saved. Linked parents receive an in-app alert; no SMS or email is sent."); return redirect(url_for("attendance",lesson_date=day,class_name=cls,subject=sub))
  students=d.execute("SELECT * FROM students WHERE class_name=? AND active=1 ORDER BY stream,full_name",(cls,)).fetchall()
  saved={r["student_id"]:r["status"] for r in d.execute("SELECT student_id,status FROM attendance WHERE lesson_date=? AND subject=?",(day,sub))}
 body="""<h1>Lesson attendance</h1><section class=panel><form method=get><div class=field><label>Date</label><input type=date name=lesson_date value='{{day}}' required></div><div class=field><label>Class</label><select name=class_name required>{% for c in classes %}<option {% if c==cls %}selected{% endif %}>{{c}}</option>{% endfor %}</select></div><div class=field><label>Subject</label><select name=subject required>{% for s in subs %}<option {% if s==sub %}selected{% endif %}>{{s}}</option>{% endfor %}{% if viewer.role=='admin' and not subs %}<option selected>General</option>{% endif %}</select></div><button>Load class</button></form></section>{% if students %}<form method=post><input type=hidden name=_csrf value='{{csrf}}'><input type=hidden name=lesson_date value='{{day}}'><input type=hidden name=class_name value='{{cls}}'><input type=hidden name=subject value='{{sub}}'><div class=table-wrap><table><tr><th>Student</th><th>Stream</th><th>Status</th></tr>{% for s in students %}<tr><td>{{s.full_name}} ({{s.admission_no}})</td><td>{{s.stream}}</td><td><select name=s{{s.id}}>{% for st in ['Present','Absent','Late'] %}<option {% if saved.get(s.id,'Present')==st %}selected{% endif %}>{{st}}</option>{% endfor %}</select></td></tr>{% endfor %}</table></div><button>Save attendance</button></form>{% else %}<p class=muted>No students in this class. Admins add students and assign teachers.</p>{% endif %}"""
 return page("Attendance",body,day=day,cls=cls,sub=sub,classes=classes,subs=subs,students=students,saved=saved)

@app.route("/reports")
@roles("admin","teacher")
def reports():
 u=who(); start=request.args.get("start",date.today().replace(day=1).isoformat()); end=request.args.get("end",date.today().isoformat())
 with conn() as d:
  params=[start,end]; filter_sql=""
  if u["role"]=="teacher":
   cs=[x["class_name"] for x in d.execute("SELECT DISTINCT class_name FROM teacher_assignments WHERE teacher_id=?",(u["id"],))]
   if not cs: rows=[]
   else:
    filter_sql=" AND s.class_name IN ("+",".join("?"*len(cs))+")"; params+=cs
    rows=d.execute("""SELECT s.admission_no,s.full_name,s.class_name,s.stream,COUNT(a.id) lessons,SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) present,SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) absent,SUM(CASE WHEN a.status='Late' THEN 1 ELSE 0 END) late FROM students s LEFT JOIN attendance a ON a.student_id=s.id AND a.lesson_date BETWEEN ? AND ? WHERE s.active=1"""+filter_sql+" GROUP BY s.id ORDER BY s.class_name,s.full_name",params).fetchall()
  if u["role"]=="admin":
   rows=d.execute("""SELECT s.admission_no,s.full_name,s.class_name,s.stream,COUNT(a.id) lessons,SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) present,SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) absent,SUM(CASE WHEN a.status='Late' THEN 1 ELSE 0 END) late FROM students s LEFT JOIN attendance a ON a.student_id=s.id AND a.lesson_date BETWEEN ? AND ? WHERE s.active=1 GROUP BY s.id ORDER BY s.class_name,s.full_name""",(start,end)).fetchall()
 if request.args.get("format")=="csv":
  out=io.StringIO(); w=csv.writer(out); w.writerow(["Admission","Student","Class","Stream","Lessons","Present","Absent","Late","Present percent"])
  for r in rows: w.writerow([r["admission_no"],r["full_name"],r["class_name"],r["stream"],r["lessons"],r["present"] or 0,r["absent"] or 0,r["late"] or 0,round((r["present"] or 0)*100/r["lessons"],1) if r["lessons"] else ""])
  resp=make_response(out.getvalue()); resp.headers["Content-Type"]="text/csv"; resp.headers["Content-Disposition"]="attachment; filename=scholar-attendance.csv"; return resp
 body="""<h1>Attendance reports</h1><section class=panel><form method=get><div class=field><label>From</label><input type=date name=start value='{{start}}' required></div><div class=field><label>To</label><input type=date name=end value='{{end}}' required></div><button>Generate report</button><a class='btn secondary' href='{{url_for("reports",start=start,end=end,format="csv")}}'>Export CSV</a></form></section><div class=table-wrap><table><tr><th>Student</th><th>Class</th><th>Lessons</th><th>Present</th><th>Absent</th><th>Late</th><th>Present %</th></tr>{% for r in rows %}<tr><td>{{r.full_name}}</td><td>{{r.class_name}} / {{r.stream}}</td><td>{{r.lessons}}</td><td>{{r.present or 0}}</td><td>{{r.absent or 0}}</td><td>{{r.late or 0}}</td><td>{% if r.lessons %}{{((r.present or 0)*100/r.lessons)|round(1)}}%{% else %}—{% endif %}</td></tr>{% endfor %}</table></div>"""
 return page("Reports",body,rows=rows,start=start,end=end)

@app.route("/calendar",methods=["GET","POST"])
@login_required
def calendar():
 with conn() as d:
  if request.method=="POST":
   if who()["role"]!="admin": abort(403)
   day=request.form.get("event_date",""); title=request.form.get("title","").strip(); detail=request.form.get("details","").strip()
   if not day or not title: flash("Date and title required.")
   else:
    d.execute("INSERT INTO events(event_date,title,details,created_by) VALUES(?,?,?,?)",(day,title,detail,who()["id"]))
    msg=f"School calendar update: {title} on {day}."
    parents=d.execute("SELECT id,username FROM users WHERE role='parent' AND active=1").fetchall()
    ncols={x["name"] for x in d.execute("PRAGMA table_info(notifications)")}
    for p in parents:
     if "recipient" in ncols: d.execute("INSERT INTO notifications(recipient,recipient_user_id,message) VALUES(?,?,?)",(p["username"],p["id"],msg))
     else: d.execute("INSERT INTO notifications(recipient_user_id,message) VALUES(?,?)",(p["id"],msg))
    d.commit(); flash("Calendar event added. Parent accounts have been notified."); return redirect(url_for("calendar"))
  events=d.execute("SELECT * FROM events ORDER BY event_date DESC").fetchall()
 body="""<h1>School calendar</h1>{% if viewer.role=='admin' %}<section class=panel><h2>Add event (visible to parents)</h2><form method=post><input type=hidden name=_csrf value='{{csrf}}'><div class=field><label>Date</label><input type=date name=event_date required></div><div class=field><label>Event</label><input name=title required></div><div class=field><label>Details</label><input name=details></div><button>Add event</button></form></section>{% endif %}<div class=table-wrap><table><tr><th>Date</th><th>Event</th><th>Details</th></tr>{% for e in events %}<tr><td>{{e.event_date}}</td><td>{{e.title}}</td><td>{{e.details}}</td></tr>{% endfor %}</table></div>"""
 return page("Calendar",body,events=events)

@app.route("/timetable",methods=["GET","POST"])
@login_required
def timetable():
 u=who()
 with conn() as d:
  if request.method=="POST":
   if u["role"]!="admin": abort(403)
   try: weekday=int(request.form.get("weekday","-1")); teacher_id=int(request.form.get("teacher_id","0"))
   except ValueError: weekday=-1; teacher_id=0
   start=request.form.get("start_time",""); end=request.form.get("end_time",""); cls=request.form.get("class_name","").strip(); subject=request.form.get("subject","").strip(); room=request.form.get("room","").strip()
   teacher=d.execute("SELECT id FROM users WHERE id=? AND role='teacher' AND active=1",(teacher_id,)).fetchone()
   if weekday not in range(7) or not start or not end or start>=end or not cls or not subject or not teacher: flash("Enter a valid day, time range, class, subject and active teacher.")
   else:
    d.execute("INSERT INTO timetable(weekday,start_time,end_time,class_name,subject,room,teacher_id) VALUES(?,?,?,?,?,?,?)",(weekday,start,end,cls,subject,room,teacher_id)); d.commit(); log("timetable_added",cls+"/"+subject); flash("Lesson added to the timetable."); return redirect(url_for("timetable"))
  teachers=d.execute("SELECT id,full_name FROM users WHERE role='teacher' AND active=1 ORDER BY full_name").fetchall()
  if u["role"]=="teacher": rows=d.execute("SELECT t.*,u.full_name teacher_name FROM timetable t JOIN users u ON u.id=t.teacher_id WHERE t.teacher_id=? ORDER BY t.weekday,t.start_time",(u["id"],)).fetchall()
  else: rows=d.execute("SELECT t.*,u.full_name teacher_name FROM timetable t JOIN users u ON u.id=t.teacher_id ORDER BY t.weekday,t.start_time,t.class_name").fetchall()
 days=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
 body="""<h1>School timetable</h1><p class=muted>Administrators manage the lesson schedule. Teachers see their own lessons; parents can view the published timetable.</p>{% if viewer.role=='admin' %}<section class=panel><h2>Schedule a lesson</h2><form method=post><input type=hidden name=_csrf value='{{csrf}}'><div class=field><label>Day</label><select name=weekday required>{% for i,day in days %}<option value={{i}}>{{day}}</option>{% endfor %}</select></div><div class=field><label>Start time</label><input type=time name=start_time required></div><div class=field><label>End time</label><input type=time name=end_time required></div><div class=field><label>Class</label><input name=class_name placeholder='Form 1' required></div><div class=field><label>Subject</label><input name=subject placeholder='Mathematics' required></div><div class=field><label>Teacher</label><select name=teacher_id required>{% for t in teachers %}<option value={{t.id}}>{{t.full_name}}</option>{% endfor %}</select></div><div class=field><label>Room (optional)</label><input name=room></div><button>Add lesson</button></form></section>{% endif %}<div class=table-wrap><table><tr><th>Day</th><th>Time</th><th>Class</th><th>Subject</th><th>Teacher</th><th>Room</th>{% if viewer.role=='admin' %}<th>Action</th>{% endif %}</tr>{% for r in rows %}<tr><td>{{days[r.weekday]}}</td><td>{{r.start_time}}–{{r.end_time}}</td><td>{{r.class_name}}</td><td>{{r.subject}}</td><td>{{r.teacher_name}}</td><td>{{r.room or '—'}}</td>{% if viewer.role=='admin' %}<td><form method=post action='{{url_for("delete_timetable",tid=r.id)}}'><input type=hidden name=_csrf value='{{csrf}}'><button class=secondary>Remove</button></form></td>{% endif %}</tr>{% else %}<tr><td colspan=7>No timetable lessons have been scheduled yet.</td></tr>{% endfor %}</table></div>"""
 return page("School timetable",body,rows=rows,teachers=teachers,days=list(enumerate(days)))

@app.route("/timetable/<int:tid>/delete",methods=["POST"])
@roles("admin")
def delete_timetable(tid):
 with conn() as d: d.execute("DELETE FROM timetable WHERE id=?",(tid,))
 log("timetable_removed",str(tid)); flash("Lesson removed from timetable."); return redirect(url_for("timetable"))

@app.route("/parent")
@roles("parent")
def parent():
 u=who()
 with conn() as d:
  kids=d.execute("SELECT * FROM students WHERE parent_user_id=? AND active=1",(u["id"],)).fetchall()
  marks=d.execute("SELECT a.*,s.full_name FROM attendance a JOIN students s ON s.id=a.student_id WHERE s.parent_user_id=? ORDER BY a.lesson_date DESC,a.id DESC LIMIT 100",(u["id"],)).fetchall()
 body="""<h1>Parents' portal</h1><p class=muted>Only children linked to your account are visible.</p>{% for k in kids %}<section class=panel><h2>{{k.full_name}}</h2>Admission {{k.admission_no}} · {{k.class_name}} / {{k.stream}}</section>{% else %}<div class=notice>No children linked yet. Contact the school administrator.</div>{% endfor %}<section class=panel><h2>Attendance history</h2><div class=table-wrap><table><tr><th>Date</th><th>Child</th><th>Subject</th><th>Status</th></tr>{% for m in marks %}<tr><td>{{m.lesson_date}}</td><td>{{m.full_name}}</td><td>{{m.subject}}</td><td>{{m.status}}</td></tr>{% endfor %}</table></div></section>"""
 return page("Parents' portal",body,kids=kids,marks=marks)

@app.route("/notifications",methods=["GET","POST"])
@login_required
def notifications():
 u=who()
 with conn() as d:
  if u["role"]=="parent":
   if request.method=="POST": d.execute("UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE id=? AND recipient_user_id=?",(request.form.get("nid"),u["id"])); d.commit()
   rows=d.execute("SELECT n.*,s.full_name student_name FROM notifications n LEFT JOIN students s ON s.id=n.student_id WHERE n.recipient_user_id=? ORDER BY n.id DESC LIMIT 100",(u["id"],)).fetchall()
  elif u["role"]=="teacher":
   if request.method=="POST": d.execute("UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE id=? AND recipient_user_id=?",(request.form.get("nid"),u["id"])); d.commit()
   rows=d.execute("SELECT n.*,s.full_name student_name FROM notifications n LEFT JOIN students s ON s.id=n.student_id WHERE n.recipient_user_id=? ORDER BY n.id DESC LIMIT 100",(u["id"],)).fetchall()
  elif u["role"]=="admin": rows=d.execute("SELECT n.*,s.full_name student_name,u.full_name recipient FROM notifications n LEFT JOIN students s ON s.id=n.student_id LEFT JOIN users u ON u.id=n.recipient_user_id ORDER BY n.id DESC LIMIT 100").fetchall()
  else: rows=[]
 body="""<h1>Notifications</h1><div class=notice>In-app alerts are available. Allow browser notifications below to receive alerts while Scholar Tracker is open. SMS, email and background push are not connected.</div>{% if viewer.role in ['parent','teacher'] %}<section class=panel><h2>Browser alerts</h2><p class=muted>Enable browser permission to see a pop-up when a new attendance alert arrives while this app is open.</p><button type=button id=enableBrowserAlerts>Enable browser notifications</button><span id=browserAlertStatus class=muted></span></section>{% endif %}{% if rows %}<div class=table-wrap><table><tr><th>Created</th>{% if viewer.role=='admin' %}<th>Parent</th>{% endif %}<th>Student</th><th>Message</th><th>Status</th></tr>{% for n in rows %}<tr><td>{{n.created_at}}</td>{% if viewer.role=='admin' %}<td>{{n.recipient or 'Unlinked'}}</td>{% endif %}<td>{{n.student_name or '—'}}</td><td>{{n.message}}</td><td>{% if viewer.role in ['parent','teacher'] and not n.read_at %}<form method=post><input type=hidden name=_csrf value='{{csrf}}'><input type=hidden name=nid value={{n.id}}><button class=secondary>Mark read</button></form>{% else %}{{'Read' if n.read_at else 'Unread'}}{% endif %}</td></tr>{% endfor %}</table></div>{% else %}<p class=muted>No notifications.</p>{% endif %}"""
 return page("Notifications",body,rows=rows)

@app.route("/api/notifications/latest")
@roles("parent","teacher")
def latest_notifications():
 u=who(); after=request.args.get("after","0")
 try: after_id=max(0,int(after))
 except (TypeError,ValueError): after_id=0
 with conn() as d:
  latest_id=d.execute("SELECT COALESCE(MAX(id),0) FROM notifications WHERE recipient_user_id=?",(u["id"],)).fetchone()[0]
  rows=d.execute("SELECT id,message,created_at FROM notifications WHERE recipient_user_id=? AND id>? ORDER BY id ASC LIMIT 20",(u["id"],after_id)).fetchall()
 return {"latest_id":latest_id,"notifications":[{"id":r["id"],"message":r["message"],"created_at":r["created_at"]} for r in rows]}

# Browser notifications work only after permission is granted and while the app is open.
SHELL = SHELL.replace("</body>", """<script>
(function(){
  const button=document.getElementById('enableBrowserAlerts');
  const status=document.getElementById('browserAlertStatus');
  if(button){
    button.addEventListener('click',async function(){
      if(!('Notification' in window)){status.textContent=' This browser does not support notifications.';return;}
      const permission=await Notification.requestPermission();
      status.textContent=permission==='granted'?' Browser notifications enabled.':' Permission not granted.';
    });
  }
  if(!('fetch' in window)) return;
  let lastId=0, ready=false;
  async function poll(){
    try{
      const response=await fetch('/api/notifications/latest?after='+lastId,{cache:'no-store'});
      if(!response.ok) return;
      const data=await response.json();
      if(!ready){
        lastId=Math.max(lastId,data.latest_id||0);ready=true;
        const recent=(data.notifications||[]).filter(item=>(Date.now()-new Date(item.created_at+'Z').getTime())<90000);
        for(const item of recent){
          if('Notification' in window && Notification.permission==='granted') new Notification('Scholar Tracker',{body:item.message,tag:'scholar-'+item.id});
        }
        return;
      }
      for(const item of data.notifications||[]){
        lastId=Math.max(lastId,item.id);
        if('Notification' in window && Notification.permission==='granted'){
          new Notification('Scholar Tracker', {body:item.message,tag:'scholar-'+item.id});
        }
      }
    }catch(error){ /* Keep the app usable if notifications are unavailable. */ }
  }
  if(document.querySelector('a[href*="/notifications"]')){poll();setInterval(poll,30000);}
})();
</script></body>""")

@app.route("/health")
def health(): return {"status":"ok","app":"Scholar Tracker","published":False}
@app.errorhandler(403)
def denied(e): return page("Access denied","<h1>Access denied</h1><p>Your account cannot access this page.</p>"),403
@app.errorhandler(404)
def missing(e): return page("Not found","<h1>Not found</h1>"),404
@app.errorhandler(400)
def bad(e): return page("Request blocked","<h1>Request blocked</h1><p>Refresh and try again, or sign in again.</p>"),400
init()
if __name__=="__main__": app.run(host="127.0.0.1",port=int(os.environ.get("PORT","5000")),debug=False)
