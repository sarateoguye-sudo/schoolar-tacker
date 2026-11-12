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
        for path in ("/attendance-risk", "/unmarked-registers", "/notices", "/champion-tasks", "/audit-log"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login", response.headers["Location"])

    def test_parent_notices_only_show_published_items(self):
        with scholar_app.connect_db() as db:
            db.execute(
                "INSERT INTO school_notices(title,body,published,created_by) VALUES(?,?,?,?)",
                ("Public test notice", "School meeting on Friday.", 1, "test"),
            )
            db.execute(
                "INSERT INTO school_notices(title,body,published,created_by) VALUES(?,?,?,?)",
                ("Private draft", "This should not be public.", 0, "test"),
            )
            db.commit()
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
