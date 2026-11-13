"""Security regression tests for the parent portal; all records are fictional."""
import re
import secrets
from datetime import date, datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

import app as scholar_app
import parent_portal as portal

scholar_app.app.config.update(TESTING=True)


def csrf_token(response):
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    assert match, "Expected a CSRF token in the form"
    return match.group(1).decode()


def add_student(school_id=1, full_name=None):
    full_name = full_name or ("Fictional Learner " + secrets.token_hex(3))
    admission = "TEST-" + secrets.token_hex(5).upper()
    with scholar_app.connect_db() as db:
        cur = db.execute(
            """INSERT INTO students(admission_no,full_name,class_name,stream,parent_contact,school_id)
               VALUES(?,?,?,?,?,?)""",
            (admission, full_name, "Form 1", "A", "", school_id),
        )
        db.commit()
        return cur.lastrowid


def add_parent(email, student_id=None, school_id=1, password="initial-parent-password-123"):
    with scholar_app.connect_db() as db:
        cur = db.execute(
            """INSERT INTO parent_accounts(school_id,email,password_hash,email_verified_at)
               VALUES(?,?,?,?)""",
            (school_id, email, generate_password_hash(password), datetime.now(timezone.utc).isoformat()),
        )
        parent_id = cur.lastrowid
        if student_id is not None:
            db.execute(
                "INSERT INTO parent_student_links(parent_id,student_id,school_id) VALUES(?,?,?)",
                (parent_id, student_id, school_id),
            )
        db.commit()
        return parent_id


def parent_session(client, parent_id, school_id=1, version=1):
    with client.session_transaction() as sess:
        sess["role"] = "parent"
        sess["parent_id"] = parent_id
        sess["parent_school_id"] = school_id
        sess["parent_session_version"] = version


def admin_login(client):
    response = client.get("/admin/login")
    return client.post(
        "/admin/login",
        data={
            "csrf_token": csrf_token(response),
            "username": "test-admin",
            "password": "test-only-password-12345",
        },
    )


def invite_parent(client, monkeypatch, student_id, email):
    captured = {}

    def fake_send_email(recipient, subject, body):
        captured.update(recipient=recipient, subject=subject, body=body)
        return True

    monkeypatch.setattr(portal, "send_email", fake_send_email)
    admin_login(client)
    response = client.get("/admin/parent-invitations")
    response = client.post(
        "/admin/parent-invitations",
        data={
            "csrf_token": csrf_token(response),
            "student_id": str(student_id),
            "email": email,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert captured["recipient"] == email.lower()
    match = re.search(r"token=([A-Za-z0-9_-]+)", captured["body"])
    assert match, "Invitation email should contain a secure accept link"
    return match.group(1)


def test_invitation_is_emailed_hashed_single_use_and_expires(monkeypatch):
    client = scholar_app.app.test_client()
    student_id = add_student()
    token = invite_parent(client, monkeypatch, student_id, "Guardian.Example@example.test")

    with scholar_app.connect_db() as db:
        stored = db.execute(
            "SELECT token_hash,used_at,expires_at FROM parent_invitations ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert stored["token_hash"] == portal.token_digest(token)
    assert token not in stored["token_hash"]
    assert stored["used_at"] is None

    response = client.get("/parents/accept-invitation", query_string={"token": token})
    response = client.post(
        "/parents/accept-invitation",
        data={
            "csrf_token": csrf_token(response),
            "token": token,
            "password": "new-parent-password-123",
            "confirm_password": "new-parent-password-123",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/parents/portal")
    assert client.get("/parents/portal").status_code == 200
    assert client.get("/parents/accept-invitation", query_string={"token": token}).status_code == 400

    expired_token = "fictional-expired-token"
    with scholar_app.connect_db() as db:
        db.execute(
            """INSERT INTO parent_invitations(school_id,student_id,email,token_hash,expires_at,created_by)
               VALUES(?,?,?,?,?,?)""",
            (1, student_id, "expired@example.test", portal.token_digest(expired_token),
             (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat(), "test-admin"),
        )
        db.commit()
    assert client.get("/parents/accept-invitation", query_string={"token": expired_token}).status_code == 400


def test_child_reports_deny_other_parent_and_other_school():
    child_a = add_student(full_name="Fictional Learner A")
    child_b = add_student(full_name="Fictional Learner B")
    with scholar_app.connect_db() as db:
        cur = db.execute("INSERT INTO schools(name) VALUES(?)", ("Fictional School Two",))
        school_two = cur.lastrowid
        db.commit()
    child_c = add_student(school_id=school_two, full_name="Fictional Learner C")

    parent_a = add_parent("parent-a@example.test", child_a, 1)
    parent_b = add_parent("parent-b@example.test", child_b, 1)
    parent_c = add_parent("parent-c@example.test", child_c, school_two)

    with scholar_app.connect_db() as db:
        db.execute(
            "INSERT INTO attendance(student_id,lesson_date,subject,status,marked_by) VALUES(?,?,?,?,?)",
            (child_a, date.today().isoformat(), "Mathematics", "Present", "Fictional Teacher"),
        )
        db.commit()

    client_a = scholar_app.app.test_client()
    parent_session(client_a, parent_a, 1)
    report = client_a.get(f"/parents/children/{child_a}/report")
    assert report.status_code == 200
    assert b"Mathematics" in report.data
    assert b"Present" in report.data
    assert client_a.get(f"/parents/children/{child_b}/report").status_code == 404
    assert client_a.get(f"/parents/children/{child_c}/report").status_code == 404

    client_b = scholar_app.app.test_client()
    parent_session(client_b, parent_b, 1)
    assert client_b.get(f"/parents/children/{child_a}/report").status_code == 404

    client_c = scholar_app.app.test_client()
    parent_session(client_c, parent_c, school_two)
    assert client_c.get(f"/parents/children/{child_a}/report").status_code == 404
    assert client_c.get(f"/parents/children/{child_c}/report").status_code == 200


def test_parent_calendar_and_notices_are_authenticated_and_school_scoped():
    with scholar_app.connect_db() as db:
        cur = db.execute("INSERT INTO schools(name) VALUES(?)", ("Fictional Calendar School",))
        school_two = cur.lastrowid
        db.execute(
            "INSERT INTO events(event_date,title,details,school_id) VALUES(?,?,?,?)",
            (date.today().isoformat(), "School One Science Fair", "Fictional event", 1),
        )
        db.execute(
            "INSERT INTO events(event_date,title,details,school_id) VALUES(?,?,?,?)",
            (date.today().isoformat(), "School Two Private Event", "Must not leak", school_two),
        )
        db.execute(
            "INSERT INTO school_notices(title,body,published,created_by,school_id) VALUES(?,?,?,?,?)",
            ("School One Notice", "Fictional notice", 1, "test", 1),
        )
        db.execute(
            "INSERT INTO school_notices(title,body,published,created_by,school_id) VALUES(?,?,?,?,?)",
            ("School Two Notice", "Must not leak", 1, "test", school_two),
        )
        db.commit()

    child = add_student()
    parent_id = add_parent("calendar-parent@example.test", child, 1)
    anonymous = scholar_app.app.test_client()
    assert anonymous.get("/parents/calendar").status_code == 302
    assert anonymous.get("/parents/notices").status_code == 302

    client = scholar_app.app.test_client()
    parent_session(client, parent_id, 1)
    calendar = client.get("/parents/calendar")
    notices = client.get("/parents/notices")
    assert calendar.status_code == 200
    assert b"School One Science Fair" in calendar.data
    assert b"School Two Private Event" not in calendar.data
    assert notices.status_code == 200
    assert b"School One Notice" in notices.data
    assert b"School Two Notice" not in notices.data


def test_password_reset_is_single_use_and_invalidates_existing_sessions(monkeypatch):
    parent_id = add_parent("reset-parent@example.test", password="old-parent-password-123")
    old_session = scholar_app.app.test_client()
    parent_session(old_session, parent_id, 1, 1)

    sent = {}

    def fake_send_email(recipient, subject, body):
        sent.update(recipient=recipient, subject=subject, body=body)
        return True

    monkeypatch.setattr(portal, "send_email", fake_send_email)
    client = scholar_app.app.test_client()
    response = client.get("/parents/forgot-password")
    response = client.post(
        "/parents/forgot-password",
        data={"csrf_token": csrf_token(response), "email": "reset-parent@example.test"},
    )
    assert response.status_code == 302
    token_match = re.search(r"token=([A-Za-z0-9_-]+)", sent["body"])
    assert token_match
    token = token_match.group(1)

    response = client.get("/parents/reset-password", query_string={"token": token})
    response = client.post(
        "/parents/reset-password",
        data={
            "csrf_token": csrf_token(response),
            "token": token,
            "password": "replacement-parent-password-123",
            "confirm_password": "replacement-parent-password-123",
        },
    )
    assert response.status_code == 302
    assert old_session.get("/parents/portal").status_code == 302
    assert client.get("/parents/reset-password", query_string={"token": token}).status_code == 400

    login_page = client.get("/parents/login")
    failed = client.post(
        "/parents/login",
        data={"csrf_token": csrf_token(login_page), "email": "reset-parent@example.test", "password": "old-parent-password-123"},
    )
    assert b"Sign-in failed" in failed.data
    login_page = client.get("/parents/login")
    successful = client.post(
        "/parents/login",
        data={"csrf_token": csrf_token(login_page), "email": "reset-parent@example.test", "password": "replacement-parent-password-123"},
    )
    assert successful.status_code == 302
    assert successful.headers["Location"].endswith("/parents/portal")


def test_parent_post_routes_reject_missing_csrf_token():
    client = scholar_app.app.test_client()
    response = client.post("/parents/forgot-password", data={"email": "fictional@example.test"})
    assert response.status_code == 400
