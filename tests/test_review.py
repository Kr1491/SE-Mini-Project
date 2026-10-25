"""Regression checks for the supplied PR #23 review findings."""
import os
import sqlite3
import stat
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import test_access as access
from server import make_server
from study_platform.db import SCHEMA, connect, initialize
from study_platform.demo import seed
from study_platform.security import create_session, current_session, COOKIE_NAME


class ReviewTests(unittest.TestCase):
    setUp = access.AccessTests.setUp
    tearDown = access.AccessTests.tearDown
    request = access.AccessTests.request
    login_sample = access.AccessTests.login_sample

    def test_demo_refuses_an_existing_unrelated_user_without_overwriting(self):
        other = Path(self.temp.name) / 'existing.db'
        initialize(other)
        with connect(other) as db:
            db.execute("INSERT INTO users(id,name,email,role,password_hash) VALUES(1,'Real owner','real@example.test','administrator','real-password-hash')")
        with self.assertRaisesRegex(ValueError, 'own empty'):
            with connect(other) as db:
                seed(db)
        with connect(other) as db:
            row = db.execute('SELECT name,password_hash FROM users WHERE id=1').fetchone()
            self.assertEqual(tuple(row), ('Real owner', 'real-password-hash'))
            self.assertEqual(db.execute('SELECT count(*) FROM study_groups').fetchone()[0], 0)

    def test_demo_refuses_existing_group_or_nonfixture_user(self):
        for table in ['study_groups', 'users']:
            with self.subTest(table=table):
                other = Path(self.temp.name) / f'{table}.db'
                initialize(other)
                with connect(other) as db:
                    seed(db)
                    if table == 'study_groups':
                        db.execute("UPDATE study_groups SET name='Unrelated group' WHERE id=1")
                    else:
                        db.execute("INSERT INTO users(id,name,email,role) VALUES(20,'Real student','real20@example.test','student')")
                with self.assertRaises(ValueError):
                    with connect(other) as db:
                        seed(db)

    def test_fixture_database_restarts_without_changing_existing_sessions(self):
        self.login_sample(1)
        with connect(self.database) as db:
            before = db.execute('SELECT count(*) FROM sessions').fetchone()[0]
            seed(db)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], before)
        self.assertEqual(self.request('GET', '/api/session')[0], 200)

    def test_selector_rechecks_fixture_identity_after_startup(self):
        with connect(self.database) as db:
            db.execute("UPDATE users SET password_hash='real-password' WHERE id=3")
        status, _, headers = self.request('POST', '/api/demo/session', {'user_id': 3})
        self.assertEqual(status, 409)
        self.assertNotIn('Set-Cookie', headers)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)

    def test_session_schema_rejects_null_token_hash(self):
        with connect(self.database) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES(NULL,1,?,9999999999)', ('csrf',))

    def test_existing_nullable_session_table_is_migrated_without_losing_valid_provenance(self):
        legacy = Path(self.temp.name) / 'nullable.db'
        with sqlite3.connect(legacy) as db:
            db.executescript(SCHEMA.replace('token_hash TEXT PRIMARY KEY NOT NULL', 'token_hash TEXT PRIMARY KEY'))
        with connect(legacy) as db:
            seed(db)
            token, _ = create_session(db, 1)
            db.execute('INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES(NULL,1,?,9999999999)', ('bad-csrf',))
        initialize(legacy)
        with connect(legacy) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 1)
            user = current_session(db, f'{COOKIE_NAME}={token}')
            self.assertEqual(user['id'], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES(NULL,1,?,9999999999)', ('csrf',))

    @unittest.skipUnless(os.name == 'posix', 'POSIX file permissions')
    def test_database_is_private_even_with_permissive_umask(self):
        private = Path(self.temp.name) / 'new-private' / 'auth.db'
        previous = os.umask(0o022)
        try:
            initialize(private)
        finally:
            os.umask(previous)
        self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(private.parent.stat().st_mode), 0o700)

    @unittest.skipUnless(os.name == 'posix', 'POSIX file permissions')
    def test_existing_database_permissions_are_tightened(self):
        os.chmod(self.database, 0o644)
        initialize(self.database)
        self.assertEqual(stat.S_IMODE(self.database.stat().st_mode), 0o600)

    @unittest.skipUnless(os.name == 'posix', 'POSIX file permissions')
    def test_existing_shared_parent_is_refused_without_changing_its_permissions(self):
        shared = Path(self.temp.name) / 'shared'
        shared.mkdir()
        os.chmod(shared, 0o755)
        with self.assertRaisesRegex(PermissionError, '0700'):
            initialize(shared / 'auth.db')
        self.assertFalse((shared / 'auth.db').exists())
        self.assertEqual(stat.S_IMODE(shared.stat().st_mode), 0o755)

    @unittest.skipUnless(hasattr(os, 'O_NOFOLLOW'), 'No-follow file open support')
    def test_database_symlink_is_not_followed(self):
        target = Path(self.temp.name) / 'target.txt'
        target.write_text('Do not change')
        link = Path(self.temp.name) / 'link.db'
        link.symlink_to(target)
        with self.assertRaises(OSError):
            initialize(link)
        self.assertEqual(target.read_text(), 'Do not change')

    def test_ipv6_is_explicitly_rejected_instead_of_reaching_ipv4_binding(self):
        for demo in [False, True]:
            with patch('server.ThreadingHTTPServer') as http:
                with self.assertRaisesRegex(ValueError, 'IPv6'):
                    make_server(self.database, host='::1', demo=demo)
                http.assert_not_called()

    def test_supported_ipv4_demo_host_reaches_server_construction(self):
        with patch('server.ThreadingHTTPServer', return_value=SimpleNamespace()) as http:
            server = make_server(self.database, host='127.0.0.1', demo=True)
        self.assertTrue(server.demo)
        http.assert_called_once()


if __name__ == '__main__':
    unittest.main()
