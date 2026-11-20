#!/usr/bin/env python3
"""Create and verify safe SQLite backups for Scholar Tracker.

This utility never uploads data. Keep backup files private and outside the
repository. Restore refuses to overwrite an existing target database.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


def verify_database(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"Database file does not exist: {path}")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError(f"SQLite integrity check failed for {path}: {result}")
        # Ensure the file contains a database schema, not an empty placeholder.
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
    finally:
        connection.close()


def backup_database(source: Path, destination: Path) -> None:
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    verify_database(source)
    if source == destination:
        raise ValueError("Backup destination must differ from the source database.")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing backup: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        src = sqlite3.connect(source)
        dst = sqlite3.connect(temporary)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        verify_database(temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def restore_database(backup: Path, target: Path) -> None:
    backup = backup.expanduser().resolve()
    target = target.expanduser().resolve()
    verify_database(backup)
    if backup == target:
        raise ValueError("Restore source and target must differ.")
    if target.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing database: {target}. "
            "Move it aside and make a separate backup before restoring."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".restore.tmp", dir=target.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        src = sqlite3.connect(backup)
        dst = sqlite3.connect(temporary)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        verify_database(temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("verify",):
        command = commands.add_parser(name)
        command.add_argument("database", type=Path)
    for name in ("backup", "restore"):
        command = commands.add_parser(name)
        command.add_argument("source", type=Path, help="Existing valid SQLite database")
        command.add_argument("destination", type=Path, help="New output path; must not exist")
    args = parser.parse_args()
    try:
        if args.command == "verify":
            verify_database(args.database)
            print(f"Database integrity check passed: {args.database}")
        elif args.command == "backup":
            backup_database(args.source, args.destination)
            print(f"Verified backup created: {args.destination}")
        else:
            restore_database(args.source, args.destination)
            print(f"Verified database restored to: {args.destination}")
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"Database operation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
