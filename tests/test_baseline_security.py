"""Additional baseline security regression tests using fictional records.

These checks supplement feature tests; they are not a penetration test.
"""
import os
import tempfile
import unittest

import app as scholar_app
from werkzeug.security import generate_password_hash


class BaselineSecurityTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        scholar_app.app.config.update(
            TESTING=True,
            DATABASE=self.db_path,
            SECRET_KEY="baseline-security-test-secret",
            SESSION_COOKIE_SECURE=False,
        )
        scholar_app.init_db()
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("INSERT INTO schools (id, name) VALUES (1, 'Fictional Security Test School')")
            db.execute(
                """INSERT INTO users
                   (id, school_id, full_name, email, role, password_hash)
                   VALUES (1, 1, 'Test Administrator', 'security-admin@example.test',
                           'administrator', ?)""",
                (generate_password_hash("fictional-test-password-123"),),
            )
            db.commit()
        self.client = scholar_app.app.test_client()

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass

    def login(self):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            csrf = session["_csrf_token"]
        return self.client.post(
            "/login",
            data={
                "_csrf_token": csrf,
                "email": "security-admin@example.test",
                "password": "fictional-test-password-123",
            },
            follow_redirects=False,
        )

    def test_baseline_security_headers_are_present(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(
            response.headers.get("Referrer-Policy"),
            "strict-origin-when-cross-origin",
        )
        self.assertIn("default-src 'self'", response.headers.get("Content-Security-Policy", ""))

    def test_post_without_csrf_token_is_rejected(self):
        response = self.client.post("/login", data={
            "email": "security-admin@example.test",
            "password": "fictional-test-password-123",
        })
        self.assertEqual(response.status_code, 400)

    def test_deactivated_account_session_is_invalidated(self):
        self.assertIn(self.login().status_code, (302, 303))
        with scholar_app.app.app_context():
            db = scholar_app.get_db()
            db.execute("UPDATE users SET is_active=0 WHERE id=1")
            db.commit()
        response = self.client.get("/dashboard", follow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertIn("/login", response.headers.get("Location", ""))
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)


if __name__ == "__main__":
    unittest.main()
