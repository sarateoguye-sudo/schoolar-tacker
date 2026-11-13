"""Regression tests for online-only resilience features."""
import os
import re
import tempfile
import unittest

_db_file = tempfile.NamedTemporaryFile(prefix="scholar-resilience-test-", suffix=".db", delete=False)
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


class ResilienceTests(unittest.TestCase):
    def setUp(self):
        self.client = client_factory()

    def login_admin(self):
        response = self.client.get("/admin/login")
        token = csrf_token(response)
        return self.client.post(
            "/admin/login",
            data={"csrf_token": token, "username": "test-admin", "password": "test-only-password-12345"},
        )

    def test_admin_resilience_pages_require_admin(self):
        for path in ("/attendance-risk", "/unmarked-registers", "/notices", "/champion-tasks", "/audit-log", "/admin/parent-invitations"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login", response.headers["Location"])

    def test_parent_notices_only_show_published_items_after_parent_sign_in(self):
        with scholar_app.connect_db() as db:
            db.execute(
                "INSERT INTO school_notices(title,body,published,created_by,school_id) VALUES(?,?,?,?,?)",
                ("Public test notice", "School meeting on Friday.", 1, "test", 1),
            )
            db.execute(
                "INSERT INTO school_notices(title,body,published,created_by,school_id) VALUES(?,?,?,?,?)",
                ("Private draft", "This should not be public.", 0, "test", 1),
            )
            cur = db.execute(
                "INSERT INTO parent_accounts(school_id,email,password_hash,email_verified_at) VALUES(?,?,?,?)",
                (1, "resilience-parent@example.test", "not-used-in-this-test", "2026-11-13T00:00:00+00:00"),
            )
            parent_id = cur.lastrowid
            db.commit()
        anonymous = self.client.get("/parents/notices")
        self.assertEqual(anonymous.status_code, 302)
        with self.client.session_transaction() as sess:
            sess["role"] = "parent"
            sess["parent_id"] = parent_id
            sess["parent_school_id"] = 1
            sess["parent_session_version"] = 1
        response = self.client.get("/parents/notices")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Public test notice", response.data)
        self.assertNotIn(b"Private draft", response.data)

    def test_offline_service_worker_is_removed(self):
        response = self.client.get("/static/sw.js")
        self.assertEqual(response.status_code, 404)

    def test_admin_can_open_resilience_pages(self):
        self.login_admin()
        for path in ("/attendance-risk", "/unmarked-registers", "/notices", "/champion-tasks", "/audit-log"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
