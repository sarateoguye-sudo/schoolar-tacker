"""Basic authentication and role-permission regression tests."""
import os
import tempfile
import unittest

import app as scholar_app
from werkzeug.security import generate_password_hash


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        scholar_app.app.config.update(
            TESTING=True,
            DATABASE=self.db_path,
            SECRET_KEY="test-only-secret-key",
            SESSION_COOKIE_SECURE=False,
        )
        scholar_app.init_db()
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO schools (id, name) VALUES (1, 'Test School')")
            db.execute(
                "INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (?, ?, ?, ?, ?)",
                (1, "Test Admin", "admin@example.test", "administrator", generate_password_hash("a-long-test-password")),
            )
            db.execute(
                "INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (?, ?, ?, ?, ?)",
                (1, "Test Teacher", "teacher@example.test", "teacher", generate_password_hash("another-long-test-password")),
            )
            db.commit()
        self.client = scholar_app.app.test_client()

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass

    def csrf(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            return session["_csrf_token"]

    def login(self, email, password):
        token = self.csrf()
        return self.client.post(
            "/login",
            data={"_csrf_token": token, "email": email, "password": password},
            follow_redirects=False,
        )

    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_login_requires_csrf_token(self):
        response = self.client.post("/login", data={"email": "admin@example.test", "password": "a-long-test-password"})
        self.assertEqual(response.status_code, 400)

    def test_valid_login_works(self):
        response = self.login("admin@example.test", "a-long-test-password")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.headers["Location"])
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_wrong_password_is_rejected(self):
        response = self.login("admin@example.test", "wrong-password")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Email or password is incorrect", response.data)

    def test_teacher_cannot_open_admin_area(self):
        self.login("teacher@example.test", "another-long-test-password")
        self.assertEqual(self.client.get("/admin").status_code, 403)

    def test_administrator_can_open_admin_placeholder(self):
        self.login("admin@example.test", "a-long-test-password")
        self.assertEqual(self.client.get("/admin").status_code, 200)

    def test_logout_clears_session(self):
        self.login("admin@example.test", "a-long-test-password")
        self.client.get("/dashboard")  # Login rotates the CSRF token.
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post("/logout", data={"_csrf_token": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)


    def post_school_data(self, form_data):
        self.client.get("/admin/school-data")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        data = {"_csrf_token": token, **form_data}
        return self.client.post("/admin/school-data", data=data, follow_redirects=True)

    def test_administrator_can_create_class_and_stream(self):
        self.login("admin@example.test", "a-long-test-password")
        response = self.post_school_data({
            "action": "create_class",
            "class_name": "Form 1",
            "stream": "East",
            "academic_year": "2026",
        })
        self.assertEqual(response.status_code, 200)
        with scholar_app.app.app_context():
            row = scholar_app.get_db().execute(
                "SELECT name, stream, academic_year FROM classes WHERE school_id = 1"
            ).fetchone()
        self.assertEqual(tuple(row), ("Form 1", "East", "2026"))

    def test_teacher_cannot_access_school_management(self):
        self.login("teacher@example.test", "another-long-test-password")
        self.assertEqual(self.client.get("/admin/school-data").status_code, 403)

    def test_administrator_can_register_student_in_own_class(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute(
                "INSERT INTO classes (school_id, name, stream, academic_year) VALUES (1, 'Form 2', 'West', '2026')"
            )
            db.commit()
            class_id = db.execute("SELECT id FROM classes WHERE name = 'Form 2'").fetchone()["id"]
        self.login("admin@example.test", "a-long-test-password")
        response = self.post_school_data({
            "action": "create_student",
            "student_name": "Sample Student",
            "admission_number": "TEST-001",
            "class_id": str(class_id),
        })
        self.assertEqual(response.status_code, 200)
        with scholar_app.app.app_context():
            row = scholar_app.get_db().execute(
                "SELECT school_id, class_id, full_name, admission_number FROM students WHERE admission_number = 'TEST-001'"
            ).fetchone()
        self.assertEqual(tuple(row), (1, class_id, "Sample Student", "TEST-001"))

    def test_student_cannot_be_assigned_to_another_school_class(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO schools (id, name) VALUES (2, 'Other School')")
            db.execute(
                "INSERT INTO classes (school_id, name, stream, academic_year) VALUES (2, 'Form 1', 'North', '2026')"
            )
            db.commit()
            foreign_class_id = db.execute("SELECT id FROM classes WHERE school_id = 2").fetchone()["id"]
        self.login("admin@example.test", "a-long-test-password")
        response = self.post_school_data({
            "action": "create_student",
            "student_name": "Sample Student",
            "admission_number": "TEST-OTHER",
            "class_id": str(foreign_class_id),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"does not belong to your school", response.data)
        with scholar_app.app.app_context():
            count = scholar_app.get_db().execute(
                "SELECT COUNT(*) FROM students WHERE admission_number = 'TEST-OTHER'"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_duplicate_admission_number_is_rejected(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute(
                "INSERT INTO students (school_id, admission_number, full_name) VALUES (1, 'DUP-001', 'First Sample')"
            )
            db.commit()
        self.login("admin@example.test", "a-long-test-password")
        response = self.post_school_data({
            "action": "create_student",
            "student_name": "Second Sample",
            "admission_number": "DUP-001",
            "class_id": "",
        })
        self.assertIn(b"already used in your school", response.data)
        with scholar_app.app.app_context():
            count = scholar_app.get_db().execute(
                "SELECT COUNT(*) FROM students WHERE admission_number = 'DUP-001'"
            ).fetchone()[0]
        self.assertEqual(count, 1)


    def test_new_teacher_must_change_temporary_password(self):
        self.login("admin@example.test", "a-long-test-password")
        response = self.post_school_data({
            "action": "create_teacher",
            "teacher_name": "New Teacher",
            "teacher_email": "new.teacher@example.test",
            "teacher_password": "temporary-password-123",
        })
        self.assertEqual(response.status_code, 200)
        teacher_client = scholar_app.app.test_client()
        login_page = teacher_client.get("/login")
        self.assertEqual(login_page.status_code, 200)
        with teacher_client.session_transaction() as session:
            csrf = session["_csrf_token"]
        response = teacher_client.post("/login", data={
            "_csrf_token": csrf,
            "email": "new.teacher@example.test",
            "password": "temporary-password-123",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/change-password", response.headers["Location"])
        teacher_client.get("/change-password")  # Create a fresh CSRF token after login.
        self.assertEqual(teacher_client.get("/dashboard").status_code, 302)
        self.assertIn("/change-password", teacher_client.get("/dashboard").headers["Location"])
        with teacher_client.session_transaction() as session:
            csrf = session["_csrf_token"]
        response = teacher_client.post("/change-password", data={
            "_csrf_token": csrf,
            "current_password": "temporary-password-123",
            "new_password": "my-new-strong-password-456",
            "confirm_password": "my-new-strong-password-456",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.headers["Location"])
        self.assertEqual(teacher_client.get("/dashboard").status_code, 200)

    def test_password_change_rejects_mismatched_confirmation(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute(
                "INSERT INTO users (school_id, full_name, email, role, password_hash, must_change_password) VALUES (1, 'Forced Change', 'forced@example.test', 'teacher', ?, 1)",
                (generate_password_hash("temporary-password-123"),),
            )
            db.commit()
        response = self.login("forced@example.test", "temporary-password-123")
        self.assertIn("/change-password", response.headers["Location"])
        self.client.get("/change-password")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post("/change-password", data={
            "_csrf_token": token,
            "current_password": "temporary-password-123",
            "new_password": "my-new-strong-password-456",
            "confirm_password": "different-password-789",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"do not match", response.data)


    def create_assignment_fixture(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO classes (school_id, name, stream, academic_year) VALUES (1, 'Form 3', 'North', '2026')")
            class_id = db.execute("SELECT id FROM classes WHERE school_id = 1 AND name = 'Form 3'").fetchone()["id"]
            db.execute(
                "INSERT INTO students (school_id, class_id, admission_number, full_name) VALUES (1, ?, 'ATT-001', 'Attendance Sample')",
                (class_id,),
            )
            db.commit()
        self.login("admin@example.test", "a-long-test-password")
        response = self.post_school_data({
            "action": "assign_subject",
            "teacher_id": "2",
            "class_id": str(class_id),
            "subject_name": "Mathematics",
        })
        self.assertEqual(response.status_code, 200)
        with scholar_app.app.app_context():
            assignment_id = scholar_app.get_db().execute(
                "SELECT id FROM teacher_assignments WHERE teacher_id = 2 AND class_id = ?",
                (class_id,),
            ).fetchone()["id"]
        return class_id, assignment_id

    def test_admin_can_assign_subject_to_teacher(self):
        class_id, assignment_id = self.create_assignment_fixture()
        with scholar_app.app.app_context():
            row = scholar_app.get_db().execute(
                "SELECT school_id, teacher_id, class_id, subject_name FROM teacher_assignments WHERE id = ?",
                (assignment_id,),
            ).fetchone()
        self.assertEqual(tuple(row), (1, 2, class_id, "Mathematics"))

    def test_teacher_can_mark_assigned_class_attendance(self):
        _class_id, assignment_id = self.create_assignment_fixture()
        self.client.get("/dashboard")
        with self.client.session_transaction() as session:
            logout_token = session["_csrf_token"]
        self.client.post("/logout", data={"_csrf_token": logout_token})
        self.login("teacher@example.test", "another-long-test-password")
        response = self.client.get(f"/teacher/attendance/{assignment_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Attendance Sample", response.data)
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post(
            f"/teacher/attendance/{assignment_id}",
            data={"_csrf_token": token, "attendance_date": "2026-11-19", "status_1": "present"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        with scholar_app.app.app_context():
            row = scholar_app.get_db().execute(
                "SELECT status, recorded_by FROM attendance WHERE student_id = 1 AND attendance_date = '2026-11-19' AND lesson_name = 'Mathematics'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "present")
        self.assertEqual(row["recorded_by"], 2)

    def test_teacher_cannot_access_another_teachers_assignment(self):
        _class_id, assignment_id = self.create_assignment_fixture()
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute(
                "INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (1, 'Other Teacher', 'other@example.test', 'teacher', ?)",
                (generate_password_hash("other-teacher-password-123"),),
            )
            db.commit()
        self.client.get("/dashboard")
        with self.client.session_transaction() as session:
            logout_token = session["_csrf_token"]
        self.client.post("/logout", data={"_csrf_token": logout_token})
        self.login("other@example.test", "other-teacher-password-123")
        self.assertEqual(self.client.get(f"/teacher/attendance/{assignment_id}").status_code, 404)

    def test_admin_cannot_assign_teacher_from_another_school(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO schools (id, name) VALUES (2, 'Other School')")
            db.execute(
                "INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (2, 'Outside Teacher', 'outside@example.test', 'teacher', ?)",
                (generate_password_hash("outside-teacher-password-123"),),
            )
            db.execute("INSERT INTO classes (school_id, name, stream, academic_year) VALUES (1, 'Form 4', 'South', '2026')")
            local_class_id = db.execute("SELECT id FROM classes WHERE school_id = 1 AND name = 'Form 4'").fetchone()["id"]
            outside_teacher_id = db.execute("SELECT id FROM users WHERE email = 'outside@example.test'").fetchone()["id"]
            db.commit()
        self.login("admin@example.test", "a-long-test-password")
        response = self.post_school_data({
            "action": "assign_subject",
            "teacher_id": str(outside_teacher_id),
            "class_id": str(local_class_id),
            "subject_name": "English",
        })
        self.assertIn(b"not part of your school", response.data)
        with scholar_app.app.app_context():
            count = scholar_app.get_db().execute("SELECT COUNT(*) FROM teacher_assignments").fetchone()[0]
        self.assertEqual(count, 0)


    def test_attendance_requires_status_for_every_student(self):
        class_id, assignment_id = self.create_assignment_fixture()
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute(
                "INSERT INTO students (school_id, class_id, admission_number, full_name) VALUES (1, ?, 'ATT-002', 'Second Sample')",
                (class_id,),
            )
            db.commit()
        self.client.get("/dashboard")
        with self.client.session_transaction() as session:
            logout_token = session["_csrf_token"]
        self.client.post("/logout", data={"_csrf_token": logout_token})
        self.login("teacher@example.test", "another-long-test-password")
        self.client.get("/dashboard")  # Login rotates the CSRF token.
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post(
            f"/teacher/attendance/{assignment_id}",
            data={"_csrf_token": token, "attendance_date": "2026-11-19", "status_1": "present"},
            follow_redirects=True,
        )
        self.assertIn(b"Select an attendance status for every student", response.data)
        with scholar_app.app.app_context():
            count = scholar_app.get_db().execute(
                "SELECT COUNT(*) FROM attendance WHERE attendance_date = '2026-11-19' AND lesson_name = 'Mathematics'"
            ).fetchone()[0]
        self.assertEqual(count, 0)


    def test_admin_can_view_school_attendance_reports(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO classes (school_id, name, stream, academic_year) VALUES (1, 'Form 1', 'A', '2026')")
            class_id = db.execute("SELECT id FROM classes WHERE school_id = 1 AND name = 'Form 1'").fetchone()["id"]
            db.execute("INSERT INTO students (school_id, class_id, admission_number, full_name) VALUES (1, ?, 'RPT-001', 'Report Student')", (class_id,))
            student_id = db.execute("SELECT id FROM students WHERE admission_number = 'RPT-001'").fetchone()["id"]
            db.execute("INSERT INTO attendance (student_id, class_id, attendance_date, lesson_name, status, recorded_by) VALUES (?, ?, '2026-11-19', 'Daily register', 'absent', 2)", (student_id, class_id))
            db.commit()
        self.login("admin@example.test", "a-long-test-password")
        response = self.client.get("/attendance/reports?start_date=2026-11-19&end_date=2026-11-19")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Report Student", response.data)
        self.assertIn(b"Absent", response.data)

    def test_attendance_reports_reject_reversed_date_range(self):
        self.login("admin@example.test", "a-long-test-password")
        response = self.client.get("/attendance/reports?start_date=2026-11-20&end_date=2026-11-19")
        self.assertEqual(response.status_code, 400)

    def test_student_cannot_view_attendance_reports(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (1, 'Sample Student User', 'student@example.test', 'student', ?)", (generate_password_hash("student-password-123"),))
            db.commit()
        self.login("student@example.test", "student-password-123")
        self.assertEqual(self.client.get("/attendance/reports").status_code, 403)


    def test_parent_can_view_only_administrator_linked_child(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO classes (school_id, name, stream, academic_year) VALUES (1, 'Form 2', 'North', '2026')")
            class_id = db.execute("SELECT id FROM classes WHERE name = 'Form 2' AND school_id = 1").fetchone()["id"]
            db.execute("INSERT INTO students (school_id, class_id, admission_number, full_name) VALUES (1, ?, 'PAR-001', 'Linked Child')", (class_id,))
            db.execute("INSERT INTO students (school_id, class_id, admission_number, full_name) VALUES (1, ?, 'PAR-002', 'Unlinked Child')", (class_id,))
            linked_id = db.execute("SELECT id FROM students WHERE admission_number = 'PAR-001'").fetchone()["id"]
            unlinked_id = db.execute("SELECT id FROM students WHERE admission_number = 'PAR-002'").fetchone()["id"]
            db.execute("INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (1, 'Test Parent', 'parent@example.test', 'parent', ?)", (generate_password_hash("parent-long-password-123"),))
            parent_id = db.execute("SELECT id FROM users WHERE email = 'parent@example.test'").fetchone()["id"]
            db.execute("INSERT INTO student_guardians (school_id, student_id, parent_id, relationship, verified_by) VALUES (1, ?, ?, 'Mother', 1)", (linked_id, parent_id))
            db.execute("INSERT INTO attendance (student_id, class_id, attendance_date, lesson_name, status, recorded_by) VALUES (?, ?, '2026-11-19', 'Mathematics', 'present', 2)", (linked_id, class_id))
            db.commit()
        self.login("parent@example.test", "parent-long-password-123")
        response = self.client.get(f"/parent/children/{linked_id}/attendance")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Linked Child", response.data)
        self.assertIn(b"Mathematics", response.data)
        self.assertEqual(self.client.get(f"/parent/children/{unlinked_id}/attendance").status_code, 404)

    def test_parent_cannot_link_to_student_from_another_school(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO schools (id, name) VALUES (2, 'Other School')")
            db.execute("INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (1, 'Test Parent', 'link-parent@example.test', 'parent', ?)", (generate_password_hash("parent-long-password-123"),))
            db.execute("INSERT INTO students (school_id, admission_number, full_name) VALUES (2, 'OTHER-001', 'Other School Child')")
            db.commit()
            parent_id = db.execute("SELECT id FROM users WHERE email = 'link-parent@example.test'").fetchone()["id"]
            other_student_id = db.execute("SELECT id FROM students WHERE admission_number = 'OTHER-001'").fetchone()["id"]
        self.login("admin@example.test", "a-long-test-password")
        response = self.post_school_data({"action": "link_parent", "parent_id": str(parent_id), "student_id": str(other_student_id), "relationship": "Guardian"})
        self.assertIn(b"must both belong to your school", response.data)
        with scholar_app.app.app_context():
            count = scholar_app.get_db().execute("SELECT COUNT(*) FROM student_guardians").fetchone()[0]
        self.assertEqual(count, 0)

    def test_parent_role_cannot_open_attendance_reports(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (1, 'Test Parent', 'report-parent@example.test', 'parent', ?)", (generate_password_hash("parent-long-password-123"),))
            db.commit()
        self.login("report-parent@example.test", "parent-long-password-123")
        self.assertEqual(self.client.get("/attendance/reports").status_code, 403)


    def test_admin_can_create_parent_account_and_link_student(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO classes (school_id, name, stream, academic_year) VALUES (1, 'Form 3', 'East', '2026')")
            class_id = db.execute("SELECT id FROM classes WHERE name = 'Form 3' AND school_id = 1").fetchone()["id"]
            db.execute("INSERT INTO students (school_id, class_id, admission_number, full_name) VALUES (1, ?, 'LINK-001', 'Portal Test Child')", (class_id,))
            student_id = db.execute("SELECT id FROM students WHERE admission_number = 'LINK-001'").fetchone()["id"]
            db.commit()
        self.login("admin@example.test", "a-long-test-password")
        create_response = self.post_school_data({
            "action": "create_parent",
            "parent_name": "Portal Test Parent",
            "parent_email": "portal-parent@example.test",
            "parent_password": "temporary-parent-password-123",
        })
        self.assertIn(b"Parent account created", create_response.data)
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            parent = db.execute("SELECT id, must_change_password FROM users WHERE email = 'portal-parent@example.test'").fetchone()
        self.assertIsNotNone(parent)
        self.assertEqual(parent["must_change_password"], 1)
        link_response = self.post_school_data({
            "action": "link_parent",
            "parent_id": str(parent["id"]),
            "student_id": str(student_id),
            "relationship": "Guardian",
        })
        self.assertIn(b"Parent-child link created", link_response.data)
        with scholar_app.app.app_context():
            linked = scholar_app.get_db().execute(
                "SELECT relationship, verified_by FROM student_guardians WHERE parent_id = ? AND student_id = ?",
                (parent["id"], student_id),
            ).fetchone()
        self.assertEqual(linked["relationship"], "Guardian")
        self.assertEqual(linked["verified_by"], 1)



    def test_absence_notification_is_private_deduplicated_and_corrected(self):
        class_id, assignment_id = self.create_assignment_fixture()
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute(
                "INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (1, 'Attendance Parent', 'absence-parent@example.test', 'parent', ?)",
                (generate_password_hash("parent-long-password-123"),),
            )
            parent_id = db.execute("SELECT id FROM users WHERE email = 'absence-parent@example.test'").fetchone()["id"]
            student_id = db.execute("SELECT id FROM students WHERE admission_number = 'ATT-001'").fetchone()["id"]
            db.execute(
                "INSERT INTO student_guardians (school_id, student_id, parent_id, relationship, verified_by) VALUES (1, ?, ?, 'Guardian', 1)",
                (student_id, parent_id),
            )
            db.commit()

        with self.client.session_transaction() as session:
            logout_token = session["_csrf_token"]
        self.client.post("/logout", data={"_csrf_token": logout_token})
        self.login("teacher@example.test", "another-long-test-password")

        def submit_status(status):
            self.client.get("/dashboard")
            with self.client.session_transaction() as session:
                token = session["_csrf_token"]
            return self.client.post(
                f"/teacher/attendance/{assignment_id}",
                data={"_csrf_token": token, "attendance_date": "2026-11-19", "status_1": status},
                follow_redirects=True,
            )

        response = submit_status("absent")
        self.assertIn(b"notified", response.data)
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            rows = db.execute(
                "SELECT id, user_id, title, message, is_read FROM notifications WHERE user_id = ?",
                (parent_id,),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIn("marked absent", rows[0]["message"])

        submit_status("absent")
        with scholar_app.app.app_context():
            count = scholar_app.get_db().execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id = ?", (parent_id,)
            ).fetchone()[0]
        self.assertEqual(count, 1, "Repeated submission must not create duplicate notifications.")

        submit_status("present")
        with scholar_app.app.app_context():
            row = scholar_app.get_db().execute(
                "SELECT title, message, is_read FROM notifications WHERE user_id = ?", (parent_id,)
            ).fetchone()
        self.assertEqual(row["title"], "Attendance record updated")
        self.assertIn("updated to Present", row["message"])
        self.assertEqual(row["is_read"], 1)

        with self.client.session_transaction() as session:
            logout_token = session["_csrf_token"]
        self.client.post("/logout", data={"_csrf_token": logout_token})
        self.login("absence-parent@example.test", "parent-long-password-123")
        inbox = self.client.get("/notifications")
        self.assertEqual(inbox.status_code, 200)
        self.assertIn(b"Attendance record updated", inbox.data)
        self.assertIn(b"updated to Present", inbox.data)

    def test_user_cannot_mark_another_users_notification_read(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute(
                """INSERT INTO notifications (user_id, school_id, notification_type, title, message)
                   VALUES (1, 1, 'test', 'Private notice', 'Admin-only notice')"""
            )
            db.commit()
            notification_id = db.execute("SELECT id FROM notifications WHERE title = 'Private notice'").fetchone()["id"]
        self.login("teacher@example.test", "another-long-test-password")
        self.client.get("/dashboard")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post(
            f"/notifications/{notification_id}/read",
            data={"_csrf_token": token},
        )
        self.assertEqual(response.status_code, 404)


    def test_administrator_can_publish_school_calendar_event(self):
        self.login("admin@example.test", "a-long-test-password")
        self.client.get("/school-calendar")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post("/school-calendar", data={
            "_csrf_token": token,
            "title": "Sample exam week",
            "description": "Use sample event data in tests.",
            "event_date": "2026-11-25",
            "event_type": "Exam",
            "start_time": "09:00",
            "end_time": "10:30",
            "audience": "Everyone",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sample exam week", response.data)
        with scholar_app.app.app_context():
            row = scholar_app.get_db().execute(
                "SELECT title, event_date, event_type, start_time, end_time FROM school_events WHERE school_id = 1"
            ).fetchone()
        self.assertEqual(tuple(row), ("Sample exam week", "2026-11-25", "Exam", "09:00", "10:30"))

    def test_teacher_timetable_shows_only_the_signed_in_teachers_lessons(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO classes (school_id, name, stream) VALUES (1, 'Form 1', 'East')")
            class_id = db.execute("SELECT id FROM classes WHERE name = 'Form 1'").fetchone()["id"]
            db.execute("INSERT INTO teacher_assignments (school_id, teacher_id, class_id, subject_name) VALUES (1, 2, ?, 'Mathematics')", (class_id,))
            assignment_id = db.execute("SELECT id FROM teacher_assignments WHERE teacher_id = 2").fetchone()["id"]
            db.execute("INSERT INTO timetable_entries (school_id, assignment_id, weekday, start_time, end_time, room, created_by) VALUES (1, ?, 0, '08:00', '08:40', 'Room 1', 1)", (assignment_id,))
            db.commit()
        self.login("teacher@example.test", "another-long-test-password")
        response = self.client.get("/teacher/timetable")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mathematics", response.data)
        self.assertIn(b"Room 1", response.data)
        self.assertEqual(self.client.get("/admin/timetable").status_code, 403)

    def test_timetable_rejects_overlapping_teacher_or_class_periods(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO classes (school_id, name, stream) VALUES (1, 'Form 1', 'East')")
            class_id = db.execute("SELECT id FROM classes WHERE name = 'Form 1'").fetchone()["id"]
            db.execute("INSERT INTO teacher_assignments (school_id, teacher_id, class_id, subject_name) VALUES (1, 2, ?, 'Mathematics')", (class_id,))
            assignment_id = db.execute("SELECT id FROM teacher_assignments WHERE teacher_id = 2").fetchone()["id"]
            db.execute("INSERT INTO timetable_entries (school_id, assignment_id, weekday, start_time, end_time, room, created_by) VALUES (1, ?, 0, '08:00', '08:40', 'Room 1', 1)", (assignment_id,))
            db.commit()
        self.login("admin@example.test", "a-long-test-password")
        self.client.get("/admin/timetable")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post("/admin/timetable", data={
            "_csrf_token": token,
            "assignment_id": str(assignment_id),
            "weekday": "0",
            "start_time": "08:20",
            "end_time": "09:00",
            "room": "Room 2",
        }, follow_redirects=True)
        self.assertIn(b"Timetable conflict", response.data)
        with scholar_app.app.app_context():
            count = scholar_app.get_db().execute("SELECT COUNT(*) FROM timetable_entries").fetchone()[0]
        self.assertEqual(count, 1)

    def test_administrator_can_edit_and_delete_own_calendar_event(self):
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            cursor = db.execute(
                "INSERT INTO school_events (school_id, title, event_date, created_by, event_type, audience) VALUES (1, 'Old event', '2026-11-25', 1, 'Exam', 'Everyone')"
            )
            event_id = cursor.lastrowid
            db.commit()
        self.login("admin@example.test", "a-long-test-password")
        self.client.get("/school-calendar")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post("/school-calendar", data={
            "_csrf_token": token, "action": "update_event", "event_id": str(event_id),
            "title": "Updated event", "event_date": "2026-11-26", "event_type": "Meeting",
            "audience": "Staff", "description": "Updated safely", "start_time": "09:00", "end_time": "10:00",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with scholar_app.app.app_context():
            row = scholar_app.get_db().execute("SELECT title, event_date, audience FROM school_events WHERE id=?", (event_id,)).fetchone()
        self.assertEqual(tuple(row), ("Updated event", "2026-11-26", "Staff"))
        self.client.get("/school-calendar")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post("/school-calendar", data={
            "_csrf_token": token, "action": "delete_event", "event_id": str(event_id),
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with scholar_app.app.app_context():
            count = scholar_app.get_db().execute("SELECT COUNT(*) FROM school_events WHERE id=?", (event_id,)).fetchone()[0]
        self.assertEqual(count, 0)

    def test_administrator_can_delete_timetable_period(self):
        class_id, assignment_id = self.create_assignment_fixture()
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            cursor = db.execute(
                "INSERT INTO timetable_entries (school_id, assignment_id, weekday, start_time, end_time, room, created_by) VALUES (1, ?, 0, '08:00', '08:40', 'Room 1', 1)",
                (assignment_id,),
            )
            entry_id = cursor.lastrowid
            db.commit()
        # create_assignment_fixture already signs in the administrator.
        self.client.get("/admin/timetable")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post("/admin/timetable", data={
            "_csrf_token": token, "action": "delete_period", "entry_id": str(entry_id),
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with scholar_app.app.app_context():
            count = scholar_app.get_db().execute("SELECT COUNT(*) FROM timetable_entries WHERE id=?", (entry_id,)).fetchone()[0]
        self.assertEqual(count, 0)


    def test_teacher_or_admin_can_save_academic_marks_for_assignment(self):
        class_id, assignment_id = self.create_assignment_fixture()
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute(
                "INSERT INTO students (school_id, class_id, admission_number, full_name) VALUES (1, ?, 'ACAD-001', 'Report Test Student')",
                (class_id,),
            )
            student_id = db.execute("SELECT id FROM students WHERE admission_number='ACAD-001'").fetchone()["id"]
            db.commit()
        self.client.get(f"/academic-reports?assignment_id={assignment_id}")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post("/academic-reports", data={
            "_csrf_token": token,
            "assignment_id": str(assignment_id),
            "assessment_name": "Mid-term",
            "term": "Term 1",
            "academic_year": "2026",
            "max_score": "100",
            f"score_{student_id}": "78",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with scholar_app.app.app_context():
            row = scholar_app.get_db().execute(
                "SELECT subject_name, assessment_name, term, academic_year, score, max_score FROM academic_results WHERE student_id=?",
                (student_id,),
            ).fetchone()
        self.assertEqual(tuple(row), ("Mathematics", "Mid-term", "Term 1", "2026", 78.0, 100.0))

    def test_teacher_cannot_enter_marks_for_another_teachers_assignment(self):
        class_id, assignment_id = self.create_assignment_fixture()
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute(
                "INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (1, 'Other Teacher', 'other@example.test', 'teacher', ?)",
                (generate_password_hash("a-different-test-password"),),
            )
            other_id = db.execute("SELECT id FROM users WHERE email='other@example.test'").fetchone()["id"]
            db.execute(
                "INSERT INTO teacher_assignments (school_id, teacher_id, class_id, subject_name) VALUES (1, ?, ?, 'Science')",
                (other_id, class_id),
            )
            db.commit()
        self.client.post("/logout", data={"_csrf_token": self.csrf()})
        self.login("teacher@example.test", "another-long-test-password")
        response = self.client.get(f"/academic-reports?assignment_id={assignment_id}")
        self.assertEqual(response.status_code, 404)

if __name__ == "__main__":
    unittest.main()
