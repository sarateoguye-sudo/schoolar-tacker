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


if __name__ == "__main__":
    unittest.main()
