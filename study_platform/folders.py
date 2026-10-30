"""Issue #7: authorized study-group folders, with no material operations."""
import sqlite3
import unicodedata
from .security import APIError, group_access, require_permission


def parse_group_id(value):
    if len(value) > 19 or int(value) > 9223372036854775807:
        raise APIError(400, 'Invalid study group ID.')
    return int(value)


def available_groups(db, user):
    require_permission(user, 'groups.read')
    rows = db.execute('''SELECT g.id,g.name,g.created_by FROM study_groups g
        WHERE ?='administrator' OR g.created_by=? OR EXISTS (
            SELECT 1 FROM memberships m WHERE m.group_id=g.id AND m.user_id=?)
        ORDER BY g.name,g.id''', (user['role'], user['id'], user['id']))
    return [dict(row) for row in rows]


def list_folders(db, user, group_id):
    group = group_access(db, user, group_id)
    rows = db.execute('''SELECT id,group_id,name,created_by,created_at FROM folders
        WHERE group_id=? ORDER BY name_key,id''', (group_id,))
    return {'group': group, 'folders': [dict(row) for row in rows],
            'can_create': user['role'] == 'administrator' or
                (user['role'] == 'instructor' and group['created_by'] == user['id'])}


def create_folder(db, user, group_id, raw_name):
    require_permission(user, 'folders.create')
    if not isinstance(raw_name, str):
        raise APIError(400, 'Enter a folder name.')
    name = unicodedata.normalize('NFC', raw_name.strip())
    if not 1 <= len(name) <= 80 or any(unicodedata.category(char).startswith('C') for char in name):
        raise APIError(400, 'Use 1–80 characters without control or hidden formatting characters.')
    # Hold the write transaction across authorization and creation so group or
    # membership changes cannot race the authorized write.
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    group_access(db, user, group_id, manage=True)
    # Hold the write transaction across authorization and creation so group or
    # membership changes cannot race the authorized write.
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')

    group_access(db, user, group_id, manage=True)

    try:
        cursor = db.execute(
            '''INSERT INTO folders(group_id,name,name_key,created_by)
               VALUES(?,?,?,?)''',
            (group_id, name, name.casefold(), user['id'])
        )
    except sqlite3.IntegrityError as exc:
        if 'UNIQUE constraint failed: folders.group_id, folders.name_key' in str(exc):
            raise APIError(
                409,
                'A folder with this name already exists in this group.'
            ) from exc
        raise
    return dict(db.execute('''SELECT id,group_id,name,created_by,created_at
        FROM folders WHERE id=?''', (cursor.lastrowid,)).fetchone())
