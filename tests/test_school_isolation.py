"""Cross-school authorization regression tests using fictional records."""
import os
import sqlite3
import tempfile
import unittest

import app as scholar_app
from werkzeug.security import generate_password_hash


class SchoolIsolationTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        scholar_app.app.config.update(
            TESTING=True,
            DATABASE=self.db_path,
            SECRET_KEY="school-isolation-test-secret",
            SESSION_COOKIE_SECURE=False,
        )
        scholar_app.init_db()
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.executemany(
                "INSERT INTO schools (id, name) VALUES (?, ?)",
                [(1, "Fictional School Alpha"), (2, "Fictional School Beta")],
            )
            password = generate_password_hash("test-password-long-123")
            users = [
                (1, "Alpha Admin", "alpha-admin@example.test", "administrator", password),
                (1, "Alpha Teacher", "alpha-teacher@example.test", "teacher", password),
                (1, "Alpha Parent", "alpha-parent@example.test", "parent", password),
                (2, "Beta Admin", "beta-admin@example.test", "administrator", password),
                (2, "Beta Teacher", "beta-teacher@example.test", "teacher", password),
                (2, "Beta Parent", "beta-parent@example.test", "parent", password),
            ]
            db.executemany(
                "INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (?, ?, ?, ?, ?)",
                users,
            )
            db.executemany(
                "INSERT INTO classes (id, school_id, name, stream, academic_year) VALUES (?, ?, ?, ?, ?)",
                [(1, 1, "Form 1", "Alpha", "2026"), (2, 2, "Form 1", "Beta", "2026")],
            )
            db.executemany(
                "INSERT INTO students (id, school_id, class_id, admission_number, full_name) VALUES (?, ?, ?, ?, ?)",
                [(1, 1, 1, "ALPHA-001", "Fictional Alpha Student"),
                 (2, 2, 2, "BETA-001", "Fictional Beta Student")],
            )
            alpha_teacher = db.execute(
                "SELECT id FROM users WHERE email='alpha-teacher@example.test'"
            ).fetchone()["id"]
            beta_teacher = db.execute(
                "SELECT id FROM users WHERE email='beta-teacher@example.test'"
            ).fetchone()["id"]
            db.execute(
                "INSERT INTO teacher_assignments (id, school_id, teacher_id, class_id, subject_name) VALUES (1, 1, ?, 1, 'Mathematics')",
                (alpha_teacher,),
            )
            db.execute(
                "INSERT INTO teacher_assignments (id, school_id, teacher_id, class_id, subject_name) VALUES (2, 2, ?, 2, 'Science')",
                (beta_teacher,),
            )
            db.execute(
                "INSERT INTO school_events (school_id, title, event_date, event_type, audience) VALUES (1, 'Alpha private event', '2026-11-25', 'Exam', 'Everyone')"
            )
            db.execute(
                "INSERT INTO school_events (school_id, title, event_date, event_type, audience) VALUES (2, 'Beta private event', '2026-11-25', 'Exam', 'Everyone')"
            )
            db.execute(
                "INSERT INTO seating_plans (id, school_id, class_id, title, rows_count, columns_count, status, created_by) VALUES (2, 2, 2, 'Beta private plan', 2, 2, 'published', 4)"
            )
            db.execute(
                "INSERT INTO timetable_entries (school_id, assignment_id, weekday, start_time, end_time, room, created_by) VALUES (2, 2, 0, '08:00', '08:40', 'Beta Room', 4)"
            )
            db.execute(
                "INSERT INTO notifications (user_id, school_id, notification_type, title, message) VALUES (6, 2, 'private-test', 'Beta private notice', 'Beta-only notification content')"
            )
            db.commit()
        self.client = scholar_app.app.test_client()

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass

    def login(self, email):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        return self.client.post(
            "/login",
            data={
                "_csrf_token": token,
                "email": email,
                "password": "test-password-long-123",
            },
            follow_redirects=False,
        )

    def test_teacher_cannot_open_another_schools_attendance_assignment(self):
        self.login("alpha-teacher@example.test")
        response = self.client.get("/teacher/attendance/2")
        self.assertEqual(response.status_code, 404)

    def test_teacher_cannot_view_another_schools_academic_assignment(self):
        self.login("alpha-teacher@example.test")
        response = self.client.get("/academic-reports?assignment_id=2")
        self.assertEqual(response.status_code, 404)

    def test_parent_cannot_view_unlinked_child_attendance_or_reports(self):
        self.login("alpha-parent@example.test")
        self.assertEqual(self.client.get("/parent/children/2/attendance").status_code, 404)
        self.assertEqual(self.client.get("/parent/children/2/reports").status_code, 404)

    def test_calendar_only_shows_the_signed_in_users_school_events(self):
        self.login("alpha-admin@example.test")
        response = self.client.get("/school-calendar?month=2026-11")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Alpha private event", response.data)
        self.assertNotIn(b"Beta private event", response.data)

    def test_teacher_cannot_open_another_schools_published_seating_plan(self):
        self.login("alpha-teacher@example.test")
        self.assertEqual(self.client.get("/seating-plan/2").status_code, 404)

    def test_teacher_timetable_does_not_show_another_schools_lessons(self):
        self.login("alpha-teacher@example.test")
        response = self.client.get("/teacher/timetable")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Beta Room", response.data)
        self.assertNotIn(b"Science", response.data)

    def test_notification_inbox_does_not_show_another_users_or_schools_notice(self):
        self.login("alpha-parent@example.test")
        response = self.client.get("/notifications")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Beta private notice", response.data)
        self.assertNotIn(b"Beta-only notification content", response.data)

    def test_admin_cannot_create_student_in_another_schools_class(self):
        self.login("alpha-admin@example.test")
        self.client.get("/admin/school-data")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post(
            "/admin/school-data",
            data={
                "_csrf_token": token,
                "action": "create_student",
                "student_name": "Unauthorized Fictional Student",
                "admission_number": "BAD-001",
                "class_id": "2",
            },
            follow_redirects=True,
        )
        self.assertIn(b"does not belong to your school", response.data)
        with scholar_app.app.app_context():
            row = scholar_app.get_db().execute(
                "SELECT id FROM students WHERE admission_number='BAD-001'"
            ).fetchone()
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
