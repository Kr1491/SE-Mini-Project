"""Minimal shared schema for authenticated role/group access (issue #5)."""
import sqlite3
import os
import stat
from contextlib import contextmanager
from pathlib import Path

MATERIALS_SCHEMA = """
CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES study_groups(id),
        folder_id INTEGER REFERENCES folders(id),
    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 160),
    original_name TEXT NOT NULL CHECK(length(original_name) BETWEEN 1 AND 255),
    stored_name TEXT NOT NULL UNIQUE CHECK(length(stored_name) BETWEEN 1 AND 180),
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    size_bytes INTEGER NOT NULL CHECK(typeof(size_bytes)='integer' AND size_bytes>=0),
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

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
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS memberships (
    group_id INTEGER NOT NULL REFERENCES study_groups(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    PRIMARY KEY(group_id,user_id)
);
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES study_groups(id),
    name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 80),
    name_key TEXT NOT NULL CHECK(length(name_key)>0),
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id,name_key)
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id),
    csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL,
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK(is_demo IN (0,1))
);
CREATE INDEX IF NOT EXISTS memberships_user ON memberships(user_id);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
""" + MATERIALS_SCHEMA + """
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


def _migrate_upload_materials(db):
    """Preserve records from the #11 filename-only schema in the shared schema."""
    columns = {row['name'] for row in db.execute('PRAGMA table_info(materials)')}
    if {'title', 'original_name'} <= columns:
        return
    if 'filename' not in columns:
        raise ValueError('Unrecognized materials schema; existing data has been left unchanged.')
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    db.execute(MATERIALS_SCHEMA.replace('IF NOT EXISTS materials', 'materials_migrated'))
    db.execute("""INSERT INTO materials_migrated
        (id,group_id,title,original_name,stored_name,content_type,size_bytes,uploaded_by,created_at)
        SELECT id,group_id,coalesce(nullif(substr(filename,1,160),''),'Material'),filename,
               stored_name,content_type,size_bytes,uploaded_by,
               CASE WHEN typeof(created_at) IN ('integer','real')
                    THEN datetime(created_at,'unixepoch') ELSE created_at END
        FROM materials""")
    db.execute('DROP TABLE materials')
    db.execute('ALTER TABLE materials_migrated RENAME TO materials')
    db.execute('CREATE INDEX materials_group ON materials(group_id)')

def _migrate_study_group_description(db):
    """Add descriptions to existing study groups without losing data."""
    columns = {
        row['name']
        for row in db.execute('PRAGMA table_info(study_groups)')
    }

    if 'description' not in columns:
        db.execute(
            "ALTER TABLE study_groups "
            "ADD COLUMN description TEXT NOT NULL DEFAULT ''"
        )



def _migrate_material_folders(db):
    columns = {
        row['name'] for row in db.execute('PRAGMA table_info(materials)')
    }
    if 'folder_id' not in columns:
        db.execute(
            'ALTER TABLE materials ADD COLUMN folder_id '
            'INTEGER REFERENCES folders(id)'
        )
    db.execute(
        'CREATE INDEX IF NOT EXISTS materials_folder ON materials(folder_id)'
    )
def initialize(path):
    _secure_database(path)
    with connect(path) as db:
        db.executescript(SCHEMA)
        _migrate_upload_materials(db)
        _migrate_material_folders(db)
        _migrate_study_group_description(db)
        columns = {
            row['name']: row
            for row in db.execute('PRAGMA table_info(sessions)')
        }
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