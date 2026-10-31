"""Issue #18: administrator-only account role and access management."""
from urllib.parse import parse_qs
from .security import APIError, PERMISSIONS, require_permission

ROLE_LABELS = {'student': 'Student', 'instructor': 'Instructor', 'administrator': 'Administrator'}
PERMISSION_LABELS = {
    'dashboard': 'Role dashboard', 'groups.read': 'Permitted study groups',
    'materials.read': 'Permitted study materials', 'quiz.attempt': 'Student quiz attempts',
    'folders.create': 'Manage permitted group folders', 'quiz.create': 'Quiz authoring',
    'instructor.summary': 'Instructor summaries', 'admin.summary': 'Platform administration',
}
AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_access_audit (
    id INTEGER PRIMARY KEY,
    actor_id INTEGER NOT NULL REFERENCES users(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    old_role TEXT NOT NULL,
    new_role TEXT NOT NULL,
    old_is_active INTEGER NOT NULL CHECK(old_is_active IN (0,1)),
    new_is_active INTEGER NOT NULL CHECK(new_is_active IN (0,1)),
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS user_access_audit_user ON user_access_audit(user_id,id);
"""


def require_administrator(db, actor):
    # Re-read the account inside the write transaction: stale sessions/requests
    # cannot retain management authority after another admin removes it.
    current = db.execute('SELECT id,role,is_active FROM users WHERE id=?', (actor['id'],)).fetchone()
    if current is None or not current['is_active']:
        raise APIError(401, 'Your account is unavailable. Sign in again.')
    require_permission(current, 'admin.summary')
    if current['role'] != 'administrator':
        raise APIError(403, 'Administrator access is required.')
    return current


def role_options():
    return [{'value': role, 'label': label,
             'permissions': [PERMISSION_LABELS.get(value, value) for value in PERMISSIONS[role]]}
            for role, label in ROLE_LABELS.items()]


def public_user(row, viewer_id):
    return {'id': row['id'], 'name': row['name'], 'email': row['email'], 'role': row['role'],
            'is_active': bool(row['is_active']), 'version': row['access_version'],
            'is_you': row['id'] == viewer_id,
            'permissions': list(PERMISSIONS[row['role']])}


def integer(raw, *, maximum=9223372036854775807, minimum=0):
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
        raise APIError(400, 'Invalid account ID or page value.')
    canonical = raw.lstrip('0') or '0'
    if len(canonical) > len(str(maximum)):
        raise APIError(400, 'Invalid account ID or page value.')
    number = int(canonical)
    if not minimum <= number <= maximum:
        raise APIError(400, 'Invalid account ID or page value.')
    return number


def query_options(query):
    try:
        params = parse_qs(query, keep_blank_values=True, max_num_fields=8)
    except ValueError:
        raise APIError(400, 'Too many search options.')
    for key in ('q', 'role', 'access', 'limit', 'offset'):
        if len(params.get(key, [])) > 1:
            raise APIError(400, 'Provide each search option once.')
    q = params.get('q', [''])[0].strip()
    role = params.get('role', [''])[0]
    access = params.get('access', ['all'])[0]
    try: q.encode('utf-8')
    except UnicodeError: raise APIError(400, 'Enter valid search text.')
    if len(q) > 100 or (role and role not in ROLE_LABELS) or access not in ('all', 'active', 'inactive'):
        raise APIError(400, 'Invalid search, role or access filter.')
    return {'q': q, 'role': role, 'access': access,
            'limit': integer(params.get('limit', ['20'])[0], minimum=1, maximum=50),
            'offset': integer(params.get('offset', ['0'])[0])}


def list_users(db, actor, *, q='', role='', access='all', limit=20, offset=0, read_only=False):
    viewer = require_administrator(db, actor)
    where = ['1=1']; values = []
    if q:
        literal = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        where.append("(name LIKE ? ESCAPE '\\' OR email LIKE ? ESCAPE '\\')")
        values.extend(['%' + literal + '%'] * 2)
    if role:
        where.append('role=?'); values.append(role)
    if access != 'all':
        where.append('is_active=?'); values.append(int(access == 'active'))
    clause = ' AND '.join(where)
    total = db.execute('SELECT count(*) FROM users WHERE ' + clause, values).fetchone()[0]
    rows = db.execute('SELECT id,name,email,role,is_active,access_version FROM users WHERE ' + clause +
                      ' ORDER BY name COLLATE NOCASE,id LIMIT ? OFFSET ?', (*values, limit, offset))
    return {'users': [public_user(row, viewer['id']) for row in rows], 'total': total,
            'limit': limit, 'offset': offset, 'roles': role_options(), 'read_only': read_only}


def update_user_access(db, actor, user_id, data):
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    viewer = require_administrator(db, actor)
    if not isinstance(data, dict) or set(data) != {'role', 'is_active', 'version'}:
        raise APIError(400, 'Provide role, is_active and the account version.')
    if not isinstance(data['role'], str) or data['role'] not in ROLE_LABELS or type(data['is_active']) is not bool:
        raise APIError(400, 'Choose a supported role and account access status.')
    if type(data['version']) is not int or data['version'] < 0:
        raise APIError(400, 'Invalid account version. Refresh the list.')
    row = db.execute('SELECT id,name,email,role,is_active,access_version FROM users WHERE id=?', (user_id,)).fetchone()
    if row is None:
        raise APIError(404, 'Account not found.')
    if row['access_version'] != data['version']:
        raise APIError(409, 'This account changed since you opened it. The list will refresh; review it before saving again.')
    active = int(data['is_active'])
    if row['role'] == data['role'] and row['is_active'] == active:
        return {'user': public_user(row, viewer['id']), 'changed': False, 'message': 'No account changes were needed.'}
    if user_id == viewer['id']:
        raise APIError(409, 'You cannot change your own role or suspend your own account.')
    if row['role'] == 'administrator' and row['is_active'] and (data['role'] != 'administrator' or not active):
        count = db.execute("SELECT count(*) FROM users WHERE role='administrator' AND is_active=1").fetchone()[0]
        if count <= 1:
            raise APIError(409, 'At least one active administrator must remain.')
    db.execute('UPDATE users SET role=?,is_active=?,access_version=access_version+1 WHERE id=?',
               (data['role'], active, user_id))
    db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
    db.execute('''INSERT INTO user_access_audit(actor_id,user_id,old_role,new_role,old_is_active,new_is_active)
                  VALUES(?,?,?,?,?,?)''', (viewer['id'], user_id, row['role'], data['role'], row['is_active'], active))
    updated = db.execute('SELECT id,name,email,role,is_active,access_version FROM users WHERE id=?', (user_id,)).fetchone()
    return {'user': public_user(updated, viewer['id']), 'changed': True,
            'message': 'Account updated. Existing sessions for this user have been signed out.'}
