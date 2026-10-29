"""Issue #5: HTTP-handler/SQLite integration tests without a TCP listener."""
import hashlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sqlite3

from server import Handler
from study_platform.db import connect, initialize
from study_platform.demo import seed
from study_platform.security import COOKIE_NAME, create_session


class MemoryConnection:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()

    def makefile(self, *args, **kwargs):
        return self.input

    def sendall(self, data):
        self.output.write(data)


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / 'access.db'
        initialize(self.database)
        with connect(self.database) as db:
            seed(db)
        self.server = SimpleNamespace(database=self.database, demo=True)
        self.cookie = ''
        self.csrf = ''

    def tearDown(self):
        self.temp.cleanup()

    def request(self, method, path, data=None, csrf=True, headers=None, raw=None):
        request_headers = {'Host': '127.0.0.1:8000', 'Connection': 'close', 'Cookie': self.cookie}
        if csrf:
            request_headers['X-CSRF-Token'] = self.csrf
        body = b'' if data is None else json.dumps(data).encode()
        if data is not None:
            request_headers['Content-Type'] = 'application/json'
        if raw is not None:
            body = raw
        if body:
            request_headers['Content-Length'] = str(len(body))
        request_headers.update(headers or {})
        raw_request = (f'{method} {path} HTTP/1.1\r\n' + ''.join(
            f'{key}: {value}\r\n' for key, value in request_headers.items()) + '\r\n').encode() + body
        connection = MemoryConnection(raw_request)
        Handler(connection, ('127.0.0.1', 12345), self.server)
        head, content = connection.output.getvalue().split(b'\r\n\r\n', 1)
        lines = head.decode().split('\r\n')
        status = int(lines[0].split()[1])
        response_headers = dict(line.split(': ', 1) for line in lines[1:])
        if content and response_headers.get('Content-Type', '').startswith('application/json'):
            content = json.loads(content)
        if method != 'HEAD':
            self.assertEqual(int(response_headers['Content-Length']), len(connection.output.getvalue().split(b'\r\n\r\n', 1)[1]))
        return status, content, response_headers

    def login_sample(self, user_id):
        status, body, headers = self.request('POST', '/api/demo/session', {'user_id': user_id})
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        self.csrf = body['csrf_token']
        return headers

    def test_anonymous_protected_requests_are_denied(self):
        for path in ['/api/session', '/api/access/admin', '/api/access/instructor', '/api/access/groups/1']:
            self.assertEqual(self.request('GET', path)[0], 401)

    def test_permissions_match_all_three_roles(self):
        for uid, role, author, admin in [(1, 'instructor', True, False), (2, 'student', False, False), (3, 'administrator', True, True)]:
            self.login_sample(uid)
            status, body, _ = self.request('GET', '/api/session')
            self.assertEqual(status, 200)
            self.assertEqual(body['user']['role'], role)
            self.assertEqual('quiz.create' in body['permissions'], author)
            self.assertEqual('admin.summary' in body['permissions'], admin)
            self.assertNotIn('password_hash', body['user'])

    def test_student_cannot_use_instructor_quiz_or_admin_functions(self):
        self.login_sample(2)
        for path in ['/api/access/instructor', '/api/access/quiz-create', '/api/access/admin']:
            self.assertEqual(self.request('GET', path)[0], 403)

    def test_instructor_can_author_but_cannot_access_administration(self):
        self.login_sample(1)
        self.assertEqual(self.request('GET', '/api/access/instructor')[0], 200)
        self.assertEqual(self.request('GET', '/api/access/quiz-create')[0], 200)
        self.assertEqual(self.request('GET', '/api/access/admin')[0], 403)

    def test_administrator_can_access_restricted_functions_and_groups(self):
        self.login_sample(3)
        for path in ['/api/access/admin', '/api/access/instructor', '/api/access/quiz-create', '/api/access/groups/3', '/api/access/groups/1/manage']:
            self.assertEqual(self.request('GET', path)[0], 200)

    def test_members_and_group_owners_have_scoped_access(self):
        for uid in [1, 2]:
            self.login_sample(uid)
            self.assertEqual(self.request('GET', '/api/access/groups/1')[0], 200)
            self.assertEqual(self.request('GET', '/api/access/groups/3')[0], 403)
        self.login_sample(4)
        self.assertEqual(self.request('GET', '/api/access/groups/1')[0], 403)
        self.assertEqual(self.request('GET', '/api/access/groups/999')[0], 404)

    def test_management_requires_permission_and_group_ownership(self):
        self.login_sample(2)
        self.assertEqual(self.request('GET', '/api/access/groups/1/manage')[0], 403)
        self.login_sample(1)
        self.assertEqual(self.request('GET', '/api/access/groups/1/manage')[0], 200)
        self.assertEqual(self.request('GET', '/api/access/groups/3/manage')[0], 403)

    def test_revoked_membership_takes_effect_without_new_login(self):
        self.login_sample(2)
        self.assertEqual(self.request('GET', '/api/access/groups/1')[0], 200)
        with connect(self.database) as db:
            db.execute('DELETE FROM memberships WHERE group_id=1 AND user_id=2')
        self.assertEqual(self.request('GET', '/api/access/groups/1')[0], 403)

    def test_role_changes_and_disabled_accounts_take_effect_immediately(self):
        self.login_sample(1)
        with connect(self.database) as db:
            db.execute("UPDATE users SET role='student' WHERE id=1")
        self.assertEqual(self.request('GET', '/api/access/instructor')[0], 403)
        with connect(self.database) as db:
            db.execute('UPDATE users SET is_active=0 WHERE id=1')
        self.assertEqual(self.request('GET', '/api/session')[0], 401)

    def test_client_cannot_override_database_role_or_user_id(self):
        self.login_sample(2)
        status, _, _ = self.request('POST', '/api/access/check',
            {'permission': 'admin.summary', 'role': 'administrator', 'user_id': 3},
            headers={'X-Role': 'administrator', 'X-User-ID': '3'})
        self.assertEqual(status, 403)
        self.assertEqual(self.request('GET', '/api/access/admin?role=administrator')[0], 403)

    def test_forged_and_expired_sessions_are_denied(self):
        self.cookie = 'study_session=forged-token'
        self.assertEqual(self.request('GET', '/api/session')[0], 401)
        self.login_sample(1)
        with connect(self.database) as db:
            db.execute('UPDATE sessions SET expires_at=?', (int(time.time()) - 1,))
        self.assertEqual(self.request('GET', '/api/session')[0], 401)

    def test_cookie_flags_and_hashed_session_storage(self):
        headers = self.login_sample(1)
        for flag in ['HttpOnly', 'SameSite=Strict', 'Path=/']:
            self.assertIn(flag, headers['Set-Cookie'])
        token = self.cookie.split('=', 1)[1]
        with connect(self.database) as db:
            stored = db.execute('SELECT token_hash FROM sessions').fetchone()[0]
        self.assertEqual(stored, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotEqual(stored, token)

    def test_switching_sample_account_revokes_previous_session(self):
        self.login_sample(1)
        old = self.cookie
        self.login_sample(2)
        self.cookie = old
        self.assertEqual(self.request('GET', '/api/session')[0], 401)
        self.login_sample(1)
        self.assertEqual(self.request('GET', '/api/access/instructor')[0], 200)

    def test_json_mutations_require_valid_csrf_and_permission(self):
        self.login_sample(1)
        self.assertEqual(self.request('POST', '/api/access/check', {'permission': 'quiz.create'}, csrf=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/access/check', {'permission': 'quiz.create'}, headers={'X-CSRF-Token': 'wrong'})[0], 403)
        self.assertEqual(self.request('POST', '/api/access/check', {'permission': 'quiz.create'})[0], 200)
        self.assertEqual(self.request('POST', '/api/access/check', {'permission': 'unrecognized.permission'})[0], 403)

    def test_demo_disabled_but_authentication_helper_works_in_normal_mode(self):
        self.server.demo = False
        self.assertEqual(self.request('POST', '/api/demo/session', {'user_id': 1})[0], 404)
        with connect(self.database) as db:
            token, _ = create_session(db, 1)
        self.cookie = f'{COOKIE_NAME}={token}'
        self.assertEqual(self.request('GET', '/api/access/instructor')[0], 200)

    def test_invalid_json_and_permissions_produce_useful_errors(self):
        self.login_sample(1)
        self.assertEqual(self.request('POST', '/api/access/check', {}, raw=b'{broken')[0], 400)
        self.assertEqual(self.request('POST', '/api/access/check', {'permission': ['wrong type']})[0], 400)
        self.assertEqual(self.request('POST', '/api/demo/session', {'user_id': True})[0], 400)

    def test_dashboard_folders_and_material_schemas_coexist(self):
        self.login_sample(3)
        for path in ['/api/unknown-feature']:
            self.assertEqual(self.request('GET', path)[0], 404)
        self.assertEqual(self.request('GET', '/api/dashboard')[0], 200)
        self.assertEqual(self.request('GET', '/api/groups/1/folders')[0], 200)
        self.assertEqual(self.request('GET', '/api/materials')[0], 200)
        with connect(self.database) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'folders', 'materials'} <= tables)

    def test_assets_load_without_exposing_database_files(self):
        for path in ['/', '/app.js', '/style.css']:
            self.assertEqual(self.request('GET', path)[0], 200)
        self.login_sample(3)
        self.assertEqual(self.request('GET', '/var/issue5.db')[0], 404)

    def test_demo_session_is_rejected_in_normal_mode_after_restart(self):
        self.login_sample(3)
        self.server = SimpleNamespace(database=self.database, demo=False)
        self.assertEqual(self.request('GET', '/api/session')[0], 401)
        self.assertEqual(self.request('GET', '/api/access/admin')[0], 401)
        with connect(self.database) as db:
            token, _ = create_session(db, 3)
        self.cookie = f'{COOKIE_NAME}={token}'
        self.assertEqual(self.request('GET', '/api/access/admin')[0], 200)

    def test_non_ascii_csrf_token_is_denied_without_server_error(self):
        self.login_sample(1)
        self.assertEqual(self.request('POST', '/api/access/check',
            {'permission': 'quiz.create'}, headers={'X-CSRF-Token': 'é'})[0], 403)

    def test_out_of_range_group_ids_are_bad_requests(self):
        self.login_sample(1)
        for group_id in ['9223372036854775808', '9' * 100]:
            for suffix in ['', '/manage']:
                status, body, _ = self.request('GET', f'/api/access/groups/{group_id}{suffix}')
                self.assertEqual(status, 400)
                self.assertIn('group ID', body['error'])
        self.assertEqual(self.request('GET', '/api/access/groups/999')[0], 404)


    def test_legacy_session_migration_discards_unclassified_tokens(self):
        legacy = Path(self.temp.name) / 'legacy.db'

        db = sqlite3.connect(legacy)
        try:
            db.executescript("""
                CREATE TABLE sessions (
                    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
                    csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL
                );
            """)
            db.execute(
                'INSERT INTO sessions VALUES(?,?,?,?)',
                ('unknown-old-token', 1, 'old-csrf', int(time.time()) + 3600)
            )
            db.commit()
        finally:
            db.close()

        initialize(legacy)

        with connect(legacy) as db:
            self.assertIn(
                'is_demo',
                {row['name'] for row in db.execute('PRAGMA table_info(sessions)')}
            )
            self.assertEqual(
                db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0
            )
            seed(db)
            create_session(db, 1)

        initialize(legacy)

        with connect(legacy) as db:
            self.assertEqual(
                db.execute('SELECT count(*) FROM sessions').fetchone()[0], 1
            )


    def test_sample_token_is_committed_before_response_is_sent(self):
        original_json = Handler.json
        observed = []
        database = self.database
        def check_before_send(handler, status, data, extra=None):
            if extra and 'Set-Cookie' in extra:
                token = extra['Set-Cookie'].split(';')[0].split('=', 1)[1]
                with connect(database) as db:
                    observed.append(db.execute('SELECT 1 FROM sessions WHERE token_hash=?',
                        (hashlib.sha256(token.encode()).hexdigest(),)).fetchone() is not None)
            return original_json(handler, status, data, extra)
        with patch.object(Handler, 'json', check_before_send):
            self.login_sample(1)
        self.assertEqual(observed, [True])


    def test_student_can_join_group_and_list_joined_groups(self):
        self.login_sample(4)
        status, body, _ = self.request('POST', '/api/groups/1/join', {})
        self.assertEqual(status, 201)
        self.assertTrue(body['joined'])
        self.assertFalse(body['already_member'])

        status, body, _ = self.request('GET', '/api/groups')
        self.assertEqual(status, 200)
        self.assertIn(1, [group['id'] for group in body['groups']])

    def test_duplicate_group_join_does_not_duplicate_membership(self):
        self.login_sample(4)
        first = self.request('POST', '/api/groups/1/join', {})[0]
        second_status, body, _ = self.request('POST', '/api/groups/1/join', {})
        self.assertEqual(first, 201)
        self.assertEqual(second_status, 200)
        self.assertTrue(body['already_member'])

        with connect(self.database) as db:
            count = db.execute(
                'SELECT COUNT(*) FROM memberships WHERE group_id=1 AND user_id=4'
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_only_students_can_join_groups(self):
        self.login_sample(1)
        self.assertEqual(self.request('POST', '/api/groups/1/join', {})[0], 403)

    def test_join_group_rejects_missing_group(self):
        self.login_sample(4)
        self.assertEqual(self.request('POST', '/api/groups/999/join', {})[0], 404)


    def test_nonmember_cannot_access_group_until_joining(self):
        self.login_sample(4)
        self.assertEqual(self.request('GET', '/api/access/groups/1')[0], 403)

        status, body, _ = self.request('POST', '/api/groups/1/join', {})
        self.assertEqual(status, 201)
        self.assertEqual(self.request('GET', '/api/access/groups/1')[0], 200)

    def test_instructor_can_create_study_group(self):
        self.login_sample(1)

        status, body, _ = self.request(
            'POST',
            '/api/groups',
            {
                'name': 'Machine Learning',
                'description': 'Collaborative ML study sessions'
            }
        )

        self.assertEqual(status, 201)
        group_id = body['group']['id']
        self.assertEqual(body['group']['name'], 'Machine Learning')
        self.assertEqual(
            body['group']['description'],
            'Collaborative ML study sessions'
        )
        self.assertEqual(body['group']['created_by'], 1)

        with connect(self.database) as db:
            group = db.execute(
                'SELECT name, description, created_by '
                'FROM study_groups WHERE id = ?',
                (body['group']['id'],)
            ).fetchone()

        self.assertIsNotNone(group)
        self.assertEqual(group['name'], 'Machine Learning')
        self.assertEqual(
            group['description'],
            'Collaborative ML study sessions'
        )
        self.assertEqual(group['created_by'], 1)

        status, list_body, _ = self.request('GET', '/api/groups')
        self.assertEqual(status, 200)
        self.assertIn(
            group_id,
            [group['id'] for group in list_body['groups']]
        )

    def test_group_creation_requires_a_name(self):
        self.login_sample(1)

        for name in ['', '   ', None, 123]:
            with self.subTest(name=name):
                status, _, _ = self.request(
                    'POST',
                    '/api/groups',
                    {'name': name}
                )
                self.assertEqual(status, 400)

    def test_students_cannot_create_study_groups(self):
        self.login_sample(2)

        status, _, _ = self.request(
            'POST',
            '/api/groups',
            {'name': 'Unauthorized Group'}
        )

        self.assertEqual(status, 403)

    def test_administrators_cannot_create_study_groups(self):
        self.login_sample(3)

        status, _, _ = self.request(
            'POST',
            '/api/groups',
            {'name': 'Unauthorized Group'}
        )

        self.assertEqual(status, 403)

    def test_group_creation_requires_valid_csrf_token(self):
        self.login_sample(1)

        status, _, _ = self.request(
            'POST',
            '/api/groups',
            {'name': 'CSRF Test Group'},
            csrf=False
        )

        self.assertEqual(status, 403)

if __name__ == '__main__':
    unittest.main()
