"""Regression tests for SQLite backup, verification, and restore."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.backup_restore_db import backup_database, restore_database, verify_database


class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source.sqlite3"
        with sqlite3.connect(self.source) as db:
            db.execute("CREATE TABLE sample_records (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("INSERT INTO sample_records (value) VALUES ('fictional-test-record')")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_backup_and_restore_preserve_records(self):
        backup = self.root / "backups" / "test-backup.sqlite3"
        restored = self.root / "restored.sqlite3"
        backup_database(self.source, backup)
        verify_database(backup)
        restore_database(backup, restored)
        with sqlite3.connect(restored) as db:
            row = db.execute("SELECT value FROM sample_records").fetchone()
        self.assertEqual(row[0], "fictional-test-record")

    def test_backup_refuses_to_overwrite_existing_file(self):
        backup = self.root / "backup.sqlite3"
        backup_database(self.source, backup)
        with self.assertRaises(FileExistsError):
            backup_database(self.source, backup)

    def test_restore_refuses_to_overwrite_existing_database(self):
        backup = self.root / "backup.sqlite3"
        backup_database(self.source, backup)
        with self.assertRaises(FileExistsError):
            restore_database(backup, self.source)

    def test_invalid_backup_is_rejected(self):
        invalid = self.root / "invalid.sqlite3"
        invalid.write_text("not a SQLite database")
        with self.assertRaises((ValueError, sqlite3.Error)):
            verify_database(invalid)


if __name__ == "__main__":
    unittest.main()
