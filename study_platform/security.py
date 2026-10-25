"""Server-side permissions and reusable session helpers for the login module."""
import hashlib
import secrets
import time
from http.cookies import SimpleCookie, CookieError

COOKIE_NAME = 'study_session'
SESSION_SECONDS = 8 * 60 * 60
PERMISSIONS = {
    'student': ['dashboard', 'groups.read', 'materials.read', 'quiz.attempt'],
    'instructor': ['dashboard', 'groups.read', 'materials.read', 'folders.create', 'quiz.create', 'instructor.summary'],
    'administrator': ['dashboard', 'groups.read', 'materials.read', 'folders.create', 'quiz.create', 'instructor.summary', 'admin.summary'],
}


class APIError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def create_session(db, user_id):
    """Call ONLY after successful credential verification in Jiya's login module.

    Returns (raw_cookie_token, csrf_token); the database stores only a token hash.
    The caller must commit the database transaction and set an HttpOnly cookie.
    """
    user = db.execute('SELECT id FROM users WHERE id=? AND is_active=1', (user_id,)).fetchone()
    if not user:
        raise APIError(401, 'Account is unavailable.')
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.execute('DELETE FROM sessions WHERE expires_at <= ?', (int(time.time()),))
    db.execute('INSERT INTO sessions VALUES (?, ?, ?, ?)',
               (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, int(time.time()) + SESSION_SECONDS))
    return token, csrf


def current_session(db, cookie_header):
    cookies = SimpleCookie()
    try:
        cookies.load(cookie_header or '')
    except CookieError:
        raise APIError(401, 'Please sign in to continue.')
    token = cookies.get(COOKIE_NAME)
    if not token:
        raise APIError(401, 'Please sign in to continue.')
    row = db.execute('''SELECT u.id, u.name, u.email, u.role, s.csrf_token
        FROM sessions s JOIN users u ON u.id=s.user_id
        WHERE s.token_hash=? AND s.expires_at>? AND u.is_active=1''',
        (hashlib.sha256(token.value.encode()).hexdigest(), int(time.time()))).fetchone()
    if not row:
        raise APIError(401, 'Your session has expired. Please sign in again.')
    return dict(row)


def require_permission(user, permission):
    if permission not in PERMISSIONS.get(user['role'], []):
        raise APIError(403, 'Your role does not have permission for this action.')


def group_access(db, user, group_id, manage=False):
    group = db.execute('SELECT * FROM study_groups WHERE id=?', (group_id,)).fetchone()
    if not group:
        raise APIError(404, 'Study group not found.')
    if user['role'] == 'administrator':
        return dict(group)
    if manage:
        require_permission(user, 'folders.create')
        allowed = group['created_by'] == user['id']
    else:
        allowed = group['created_by'] == user['id'] or db.execute(
            'SELECT 1 FROM memberships WHERE group_id=? AND user_id=?', (group_id, user['id'])).fetchone()
    if not allowed:
        raise APIError(403, 'You do not have access to this study group.')
    return dict(group)
