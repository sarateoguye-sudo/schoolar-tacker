"""Security regression tests for the current Scholar Tracker Flask app."""
import os
import tempfile
import unittest

from werkzeug.security import generate_password_hash

import app as scholar_app


class SecurityTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        scholar_app.app.config.update(
            TESTING=True,
            DATABASE=self.db_path,
            SECRET_KEY="test-only-security-secret",
            SESSION_COOKIE_SECURE=False,
        )
        scholar_app.init_db()
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO schools (id, name) VALUES (1, 'Security Test School')")
            db.execute(
                "INSERT INTO users (school_id, full_name, email, role, password_hash) VALUES (1, 'Security Admin', 'security-admin@example.test', 'administrator', ?)",
                (generate_password_hash("a-long-security-test-password"),),
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

    def test_health_endpoint_is_available(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")

    def test_private_pages_require_sign_in(self):
        for path in ("/dashboard", "/admin", "/school-calendar", "/admin/timetable"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login", response.headers["Location"])

    def test_post_without_csrf_token_is_rejected(self):
        response = self.client.post(
            "/login",
            data={"email": "security-admin@example.test", "password": "a-long-security-test-password"},
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_can_sign_in_with_valid_credentials(self):
        token = self.csrf()
        response = self.client.post("/login", data={
            "_csrf_token": token,
            "email": "security-admin@example.test",
            "password": "a-long-security-test-password",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_security_headers_are_present(self):
        response = self.client.get("/health")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("frame-ancestors 'self'", response.headers.get("Content-Security-Policy", ""))


if __name__ == "__main__":
    unittest.main()
