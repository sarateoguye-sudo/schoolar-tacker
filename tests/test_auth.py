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
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        response = self.client.post("/logout", data={"_csrf_token": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)


if __name__ == "__main__":
    unittest.main()
