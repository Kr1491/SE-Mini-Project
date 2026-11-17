"""Public Student self-registration page and API."""
import unittest
from unittest.mock import patch
import test_access as access
from study_platform import auth
from study_platform.db import connect


class RegistrationTests(unittest.TestCase):
    request = access.AccessTests.request

    def setUp(self):
        # Fewer PBKDF2 rounds keep the suite fast; the stored format is unchanged.
        patcher = patch.object(auth, 'PASSWORD_ITERATIONS', 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        access.AccessTests.setUp(self)
        self.addCleanup(access.AccessTests.tearDown, self)
        self.server.demo = False
        self.cookie = ''
        self.csrf = ''
        self.password = 'correct horse battery'

    def register(self, **fields):
        data = {'name': 'New Student', 'email': 'new.student@example.test', 'password': self.password}
        data.update(fields)
        return self.request('POST', '/api/register', data, csrf=False)

    def user_count(self):
        with connect(self.database) as db:
            return db.execute('SELECT COUNT(*) FROM users').fetchone()[0]

    def test_registration_assets_are_public(self):
        for path in ['/register', '/register/', '/register.js']:
            self.assertEqual(self.request('GET', path, csrf=False)[0], 200)

    def test_registration_saves_student_and_signs_in(self):
        status, body, headers = self.register(email='  New.Student@Example.TEST ')
        self.assertEqual(status, 201)
        self.assertEqual(body['user']['role'], 'student')
        self.assertEqual(body['user']['email'], 'new.student@example.test')
        self.assertNotIn('password', body['user'])
        self.assertNotIn('password_hash', body['user'])
        with connect(self.database) as db:
            row = db.execute('SELECT * FROM users WHERE email=?', ('new.student@example.test',)).fetchone()
        self.assertIsNotNone(row)
        self.assertNotIn(self.password, row['password_hash'])
        self.assertTrue(auth.verify_password(self.password, row['password_hash']))
        self.cookie = headers['Set-Cookie'].split(';')[0]
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.csrf = body['csrf_token']
        status, dashboard, _ = self.request('GET', '/api/dashboard')
        self.assertEqual((status, dashboard['role']), (200, 'student'))

    def test_registered_account_can_sign_in_later(self):
        self.assertEqual(self.register()[0], 201)
        status, body, _ = self.request('POST', '/api/login', {'email': 'new.student@example.test', 'password': self.password}, csrf=False)
        self.assertEqual((status, body['user']['role']), (200, 'student'))

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self.assertEqual(self.register()[0], 201)
        before = self.user_count()
        status, body, headers = self.register(email='NEW.STUDENT@example.test')
        self.assertEqual(status, 409)
        self.assertIn('already exists', body['error'])
        self.assertNotIn('Set-Cookie', headers)
        self.assertEqual(self.user_count(), before)

    def test_invalid_details_and_privileged_roles_create_nothing(self):
        before = self.user_count()
        for fields in [{'name': ''}, {'name': 'x' * 81}, {'email': 'not-an-email'}, {'password': 'short'},
                       {'password': 'x' * 129}, {'name': ['list']}, {'role': 'administrator'}, {'role': 'instructor'}]:
            status, body, headers = self.register(**fields)
            self.assertEqual(status, 400, fields)
            self.assertTrue(body['error'])
            self.assertNotIn('Set-Cookie', headers)
        self.assertEqual(self.user_count(), before)

    def test_cross_origin_and_non_json_requests_are_rejected(self):
        before = self.user_count()
        status, _, _ = self.request('POST', '/api/register', {'name': 'A', 'email': 'a@example.test', 'password': self.password},
                                    csrf=False, headers={'Origin': 'https://evil.example'})
        self.assertEqual(status, 403)
        status, _, _ = self.request('POST', '/api/register', csrf=False, raw=b'name=A',
                                    headers={'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(status, 415)
        self.assertEqual(self.user_count(), before)

    def test_demo_mode_disables_registration(self):
        self.server.demo = True
        before = self.user_count()
        self.assertEqual(self.register()[0], 409)
        self.assertEqual(self.user_count(), before)


if __name__ == '__main__':
    unittest.main()
