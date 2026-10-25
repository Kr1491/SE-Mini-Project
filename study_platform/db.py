"""Minimal shared schema for authenticated role/group access (issue #5)."""
import sqlite3
import os
import stat
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT,
    role TEXT NOT NULL CHECK(role IN ('student','instructor','administrator')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1))
);
CREATE TABLE IF NOT EXISTS study_groups (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS memberships (
    group_id INTEGER NOT NULL REFERENCES study_groups(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    PRIMARY KEY(group_id,user_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id),
    csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL,
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK(is_demo IN (0,1))
);
CREATE INDEX IF NOT EXISTS memberships_user ON memberships(user_id);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES study_groups(id),
    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 160),
    original_name TEXT NOT NULL CHECK(length(original_name) BETWEEN 1 AND 255),
    stored_name TEXT NOT NULL UNIQUE CHECK(length(stored_name) BETWEEN 1 AND 180),
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    size_bytes INTEGER NOT NULL CHECK(typeof(size_bytes)='integer' AND size_bytes>=0),
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS materials_group ON materials(group_id);

"""


@contextmanager
def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def _secure_database(path):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == 'posix':
        directory = path.parent.lstat()
        if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid() or directory.st_mode & 0o077:
            raise PermissionError('Use a dedicated database directory owned by you with permissions 0700. For an existing local var directory, run: chmod 700 var')
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise PermissionError('Database must be a regular file.')
        if os.name == 'posix':
            if info.st_uid != os.getuid():
                raise PermissionError('Database must be owned by the current user.')
            os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


def initialize(path):
    _secure_database(path)
    with connect(path) as db:
        db.executescript(SCHEMA)
        columns = {row['name']: row for row in db.execute('PRAGMA table_info(sessions)')}
        if 'is_demo' not in columns or not columns['token_hash']['notnull']:
            db.execute("""CREATE TABLE sessions_migrated (
                token_hash TEXT PRIMARY KEY NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id),
                csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0 CHECK(is_demo IN (0,1))
            )""")
            # Legacy tokens without a mode cannot be trusted as real logins.
            if 'is_demo' in columns:
                db.execute("""INSERT INTO sessions_migrated
                    SELECT token_hash,user_id,csrf_token,expires_at,is_demo
                    FROM sessions WHERE token_hash IS NOT NULL""")
            db.execute('DROP TABLE sessions')
            db.execute('ALTER TABLE sessions_migrated RENAME TO sessions')
            db.execute('CREATE INDEX sessions_expiry ON sessions(expires_at)')
