import os
import re
import tempfile
import unittest

_TEST_ROOT = tempfile.TemporaryDirectory()
os.environ["SCHOLAR_DB"] = os.path.join(_TEST_ROOT.name, "import.db")
os.environ["SECRET_KEY"] = "test-only-secret-key"

import app as scholar


class ScholarTrackerTests(unittest.TestCase):
    def setUp(self):
        self.db_file = os.path.join(_TEST_ROOT.name, f"test-{id(self)}.db")
        scholar.DB = self.db_file
        scholar.app.config.update(TESTING=True, SECRET_KEY="test-only-secret-key", SESSION_COOKIE_SECURE=False)
        scholar.init()
        with scholar.conn() as db:
            db.execute("DELETE FROM attendance")
            db.execute("DELETE FROM notifications")
            db.execute("DELETE FROM timetable")
            db.execute("DELETE FROM events")
            db.execute("DELETE FROM teacher_assignments")
            db.execute("DELETE FROM students")
            db.execute("DELETE FROM users")
            self.admin_id = self._add_user(db, "admin1", "Administrator", "admin")
            self.teacher_id = self._add_user(db, "teacher1", "Teacher One", "teacher")
            self.parent_id = self._add_user(db, "parent1", "Parent One", "parent")
            self.other_parent_id = self._add_user(db, "parent2", "Parent Two", "parent")
            db.execute(
                "INSERT INTO students(admission_no,full_name,class_name,stream,parent_user_id) VALUES(?,?,?,?,?)",
                ("A001", "Student One", "Form 1", "A", self.parent_id),
            )
            db.execute(
                "INSERT INTO students(admission_no,full_name,class_name,stream,parent_user_id) VALUES(?,?,?,?,?)",
                ("B001", "Student Two", "Form 2", "B", self.other_parent_id),
            )
            db.execute(
                "INSERT INTO teacher_assignments(teacher_id,class_name,subject) VALUES(?,?,?)",
                (self.teacher_id, "Form 1", "Mathematics"),
            )
        self.client = scholar.app.test_client()

    @staticmethod
    def _add_user(db, username, full_name, role):
        from werkzeug.security import generate_password_hash
        cur = db.execute(
            "INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)",
            (username, generate_password_hash("test-password-123"), full_name, role),
        )
        return cur.lastrowid

    def login_as(self, user_id):
        with self.client.session_transaction() as sess:
            sess["uid"] = user_id
            sess["csrf"] = "test-csrf-token"

    def test_production_setup_requires_setup_token(self):
        original_env = scholar.APP_ENV
        original_token = os.environ.pop("SETUP_TOKEN", None)
        try:
            with scholar.conn() as db:
                db.execute("DELETE FROM users WHERE role='admin'")
            scholar.APP_ENV = "production"
            response = self.client.get("/setup")
            self.assertEqual(response.status_code, 503)
            self.assertIn(b"Configure SETUP_TOKEN", response.data)
        finally:
            scholar.APP_ENV = original_env
            if original_token is not None:
                os.environ["SETUP_TOKEN"] = original_token

    def test_setup_rejects_wrong_configured_token(self):
        original_env = scholar.APP_ENV
        original_token = os.environ.get("SETUP_TOKEN")
        try:
            with scholar.conn() as db:
                db.execute("DELETE FROM users WHERE role='admin'")
            scholar.APP_ENV = "production"
            os.environ["SETUP_TOKEN"] = "expected-test-token"
            response = self.client.post(
                "/setup",
                data={
                    "_csrf": "test-csrf-token",
                    "setup_token": "wrong-token",
                    "full_name": "New Admin",
                    "username": "newadmin",
                    "password": "a-long-test-password",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Invalid setup token", response.data)
        finally:
            scholar.APP_ENV = original_env
            if original_token is None:
                os.environ.pop("SETUP_TOKEN", None)
            else:
                os.environ["SETUP_TOKEN"] = original_token

    def test_health_endpoint_is_available(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")
        self.assertFalse(response.get_json()["published"])

    def test_private_pages_require_login(self):
        response = self.client.get("/students")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_parent_cannot_open_admin_student_register(self):
        self.login_as(self.parent_id)
        response = self.client.get("/students")
        self.assertEqual(response.status_code, 403)

    def test_parent_sees_only_linked_child(self):
        self.login_as(self.parent_id)
        response = self.client.get("/parent")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Student One", response.data)
        self.assertNotIn(b"Student Two", response.data)

    def test_teacher_cannot_mark_unassigned_class(self):
        self.login_as(self.teacher_id)
        response = self.client.get("/attendance?class_name=Form+2&subject=Mathematics")
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_open_assigned_attendance(self):
        self.login_as(self.teacher_id)
        response = self.client.get("/attendance?class_name=Form+1&subject=Mathematics")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Student One", response.data)
        self.assertNotIn(b"Student Two", response.data)

    def test_parent_cannot_create_calendar_event(self):
        self.login_as(self.parent_id)
        response = self.client.post(
            "/calendar",
            data={"_csrf": "test-csrf-token", "event_date": "2026-12-01", "title": "Test event"},
        )
        self.assertEqual(response.status_code, 403)

    def test_post_without_csrf_token_is_rejected(self):
        self.login_as(self.admin_id)
        response = self.client.post(
            "/calendar",
            data={"event_date": "2026-12-01", "title": "Test event"},
        )
        self.assertEqual(response.status_code, 400)

    def test_parent_notifications_api_returns_only_their_notifications(self):
        with scholar.conn() as db:
            db.execute(
                "INSERT INTO notifications(recipient_user_id,message) VALUES(?,?)",
                (self.parent_id, "Only for parent one"),
            )
            db.execute(
                "INSERT INTO notifications(recipient_user_id,message) VALUES(?,?)",
                (self.other_parent_id, "Private to parent two"),
            )
        self.login_as(self.parent_id)
        response = self.client.get("/api/notifications/latest")
        self.assertEqual(response.status_code, 200)
        messages = [item["message"] for item in response.get_json()["notifications"]]
        self.assertIn("Only for parent one", messages)
        self.assertNotIn("Private to parent two", messages)

    def test_admin_can_open_timetable_management(self):
        self.login_as(self.admin_id)
        response = self.client.get("/timetable")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Schedule a lesson", response.data)


if __name__ == "__main__":
    unittest.main()
