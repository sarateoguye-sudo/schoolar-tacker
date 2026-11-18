"""Basic regression tests for Scholar Tracker's security controls."""
import os
import re
import tempfile
import unittest

_db_file = tempfile.NamedTemporaryFile(prefix="scholar-security-test-", suffix=".db", delete=False)
_db_file.close()
os.environ["SCHOLAR_DB"] = _db_file.name
os.environ["SECRET_KEY"] = "test-only-secret-key-not-for-production"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-only-password-12345"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"

import app as scholar_app  # noqa: E402

scholar_app.app.config.update(TESTING=True)
client_factory = scholar_app.app.test_client


def csrf_token(response):
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    if not match:
        raise AssertionError("POST form did not contain a CSRF token")
    return match.group(1).decode()


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.client = client_factory()

    def test_health_endpoint_is_available(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")

    def test_school_pages_require_admin_login(self):
        for path in ("/", "/students", "/attendance", "/timetable", "/reports", "/calendar", "/notifications"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login", response.headers["Location"])

    def test_post_without_csrf_token_is_rejected(self):
        response = self.client.post("/admin/login", data={"username": "test-admin", "password": "test-only-password-12345"})
        self.assertEqual(response.status_code, 400)

    def test_admin_can_sign_in_with_configured_credentials(self):
        page = self.client.get("/admin/login")
        token = csrf_token(page)
        response = self.client.post(
            "/admin/login",
            data={"csrf_token": token, "username": "test-admin", "password": "test-only-password-12345"},
        )
        self.assertEqual(response.status_code, 302)
        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)

    def test_demo_teacher_account_is_not_accepted(self):
        page = self.client.get("/teacher/login")
        token = csrf_token(page)
        response = self.client.post(
            "/teacher/login",
            data={"csrf_token": token, "username": "teacher", "password": "Demo123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"shared demo account is disabled", response.data)

    def test_parent_portal_requires_parent_login(self):
        response = self.client.get("/parent/portal")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/parent/login", response.headers["Location"])

    def test_parent_only_sees_linked_student_attendance(self):
        # Sign in as administrator and create two fictional students.
        login_page = self.client.get("/admin/login")
        token = csrf_token(login_page)
        self.client.post(
            "/admin/login",
            data={"csrf_token": token, "username": "test-admin", "password": "test-only-password-12345"},
        )
        with scholar_app.connect_db() as db:
            first = db.execute(
                "INSERT INTO students(admission_no,full_name,class_name,stream) VALUES(?,?,?,?)",
                ("PARENTTEST001", "Linked Sample Learner", "Form 1", "A"),
            ).lastrowid
            other = db.execute(
                "INSERT INTO students(admission_no,full_name,class_name,stream) VALUES(?,?,?,?)",
                ("PARENTTEST002", "Unlinked Sample Learner", "Form 1", "B"),
            ).lastrowid
            db.execute(
                "INSERT INTO attendance(student_id,lesson_date,subject,status,marked_by) VALUES(?,?,?,?,?)",
                (first, "2026-11-18", "Mathematics", "Present", "Demo Teacher"),
            )
            db.execute(
                "INSERT INTO attendance(student_id,lesson_date,subject,status,marked_by) VALUES(?,?,?,?,?)",
                (other, "2026-11-18", "Science", "Absent", "Demo Teacher"),
            )
            db.commit()
        admin_page = self.client.get("/admin/parents")
        token = csrf_token(admin_page)
        response = self.client.post(
            "/admin/parents",
            data={
                "csrf_token": token,
                "parent_name": "Sample Guardian",
                "username": "sample-guardian",
                "password": "sample-guardian-password",
                "student_id": str(first),
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sample Guardian", response.data)
        parent_client = client_factory()
        parent_page = parent_client.get("/parent/login")
        token = csrf_token(parent_page)
        response = parent_client.post(
            "/parent/login",
            data={"csrf_token": token, "username": "sample-guardian", "password": "sample-guardian-password"},
        )
        self.assertEqual(response.status_code, 302)
        portal = parent_client.get("/parent/portal")
        self.assertEqual(portal.status_code, 200)
        self.assertIn(b"Linked Sample Learner", portal.data)
        self.assertIn(b"Mathematics", portal.data)
        self.assertNotIn(b"Unlinked Sample Learner", portal.data)
        forbidden = parent_client.get("/parent/portal?student_id=" + str(other))
        self.assertEqual(forbidden.status_code, 403)

    def test_security_headers_are_present(self):
        response = self.client.get("/health")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")



    def test_teacher_can_mark_only_explicitly_assigned_class(self):
        # Use fictional learners and named teacher accounts.
        with scholar_app.connect_db() as db:
            teacher_a = db.execute(
                "INSERT INTO teacher_users(username,teacher_name,password_hash) VALUES(?,?,?)",
                ("scope-teacher-a", "Scope Teacher A", scholar_app.generate_password_hash("teacher-a-password-123")),
            ).lastrowid
            teacher_b = db.execute(
                "INSERT INTO teacher_users(username,teacher_name,password_hash) VALUES(?,?,?)",
                ("scope-teacher-b", "Scope Teacher B", scholar_app.generate_password_hash("teacher-b-password-123")),
            ).lastrowid
            student_a = db.execute(
                "INSERT INTO students(admission_no,full_name,class_name,stream) VALUES(?,?,?,?)",
                ("SCOPEA001", "Scope Sample A", "Scope Form", "A"),
            ).lastrowid
            db.execute(
                "INSERT INTO students(admission_no,full_name,class_name,stream) VALUES(?,?,?,?)",
                ("SCOPEB001", "Scope Sample B", "Scope Form", "B"),
            )
            db.commit()

        admin = self.client
        login_page = admin.get("/admin/login")
        token = csrf_token(login_page)
        admin.post("/admin/login", data={
            "csrf_token": token, "username": "test-admin",
            "password": "test-only-password-12345",
        })
        assign_page = admin.get("/admin/teacher-assignments")
        token = csrf_token(assign_page)
        response = admin.post("/admin/teacher-assignments", data={
            "csrf_token": token, "teacher_user_id": str(teacher_a),
            "subject": "Computer Science", "class_name": "Scope Form", "stream": "A",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        assign_page = admin.get("/admin/teacher-assignments")
        token = csrf_token(assign_page)
        response = admin.post("/admin/teacher-assignments", data={
            "csrf_token": token, "teacher_user_id": str(teacher_b),
            "subject": "Science", "class_name": "Scope Form", "stream": "B",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with scholar_app.connect_db() as db:
            own_assignment = db.execute(
                "SELECT id FROM teacher_assignments WHERE teacher_user_id=? AND subject=?",
                (teacher_a, "Computer Science"),
            ).fetchone()["id"]
            other_assignment = db.execute(
                "SELECT id FROM teacher_assignments WHERE teacher_user_id=? AND subject=?",
                (teacher_b, "Science"),
            ).fetchone()["id"]

        teacher_client = client_factory()
        login_page = teacher_client.get("/teacher/login")
        token = csrf_token(login_page)
        response = teacher_client.post("/teacher/login", data={
            "csrf_token": token, "username": "scope-teacher-a",
            "password": "teacher-a-password-123",
        })
        self.assertEqual(response.status_code, 302)
        listing = teacher_client.get("/teacher/assigned-registers")
        self.assertEqual(listing.status_code, 200)
        self.assertIn(b"Computer Science", listing.data)
        self.assertNotIn(b"Science</td>", listing.data)
        self.assertEqual(teacher_client.get(f"/teacher/assigned-registers/{other_assignment}").status_code, 403)

        page = teacher_client.get(f"/teacher/assigned-registers/{own_assignment}")
        token = csrf_token(page)
        response = teacher_client.post(
            f"/teacher/assigned-registers/{own_assignment}",
            data={"csrf_token": token, "lesson_date": "2026-11-18", f"status_{student_a}": "Present"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        with scholar_app.connect_db() as db:
            saved = db.execute(
                "SELECT status,marked_by FROM attendance WHERE student_id=? AND lesson_date=? AND subject=?",
                (student_a, "2026-11-18", "Computer Science"),
            ).fetchone()
        self.assertEqual(saved["status"], "Present")
        self.assertEqual(saved["marked_by"], "Scope Teacher A")

if __name__ == "__main__":
    unittest.main()
