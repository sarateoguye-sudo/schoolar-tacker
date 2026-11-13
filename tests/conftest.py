"""Shared isolated environment for the Scholar Tracker test suite."""
import os
import tempfile

fd, _test_db_path = tempfile.mkstemp(prefix="scholar-parent-tests-", suffix=".db")
os.close(fd)
os.environ["SCHOLAR_DB"] = _test_db_path
os.environ["SECRET_KEY"] = "test-only-secret-key-never-use-in-production"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-only-password-12345"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"
