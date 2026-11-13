"""Stable test environment for GitHub Actions."""
import os
import tempfile

fd, path = tempfile.mkstemp(prefix="scholar-ci-", suffix=".db")
os.close(fd)
os.environ["SCHOLAR_DB"] = path
os.environ["SECRET_KEY"] = "test-only-secret-key-never-use-in-production"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-only-password-12345"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"

import app as scholar_app
scholar_app.app.config["RATELIMIT_ENABLED"] = False
