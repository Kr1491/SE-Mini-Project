"""Credential/session integration for the basic sign-in page."""
import hashlib
import unittest
from unittest.mock import patch
import server
import test_access as access
from study_platform import auth
from study_platform.auth import hash_password
from study_platform.db import connect
from study_platform.security import COOKIE_NAME


class LoginTests(unittest.TestCase):
    request = access.AccessTests.request
    tearDown = access.AccessTests.tearDown

    @classmethod
    def setUpClass(cls):
        cls.password = 'A test password 42!'
        cls.encoded = hash_password(cls.password)

    def setUp(self):
        access.AccessTests.setUp(self)
        self.server.demo = False
        with connect(self.database) as db:
            db.execute('UPDATE users SET password_hash=? WHERE id IN (1,2,3)', (self.encoded,))

    def sign_in(self, email='student@example.test', password=None, **options):
        return self.request('POST', '/api/login', {'email': email, 'password': self.password if password is None else password}, **options)

    def adopt(self, body, headers):
        self.cookie = headers['Set-Cookie'].split(';')[0]
        self.csrf = body['csrf_token']

    def test_login_assets_are_public(self):
        for path in ['/login', '/login/', '/login.js', '/login.css']:
            self.assertEqual(self.request('GET', path)[0], 200)

    def test_existing_accounts_reach_their_role_dashboard(self):
        for email, role in [('student@example.test','student'), ('instructor@example.test','instructor'), ('admin@example.test','administrator')]:
            status, body, headers = self.sign_in(email)
            self.assertEqual(status, 200)
            self.assertEqual(body['user']['role'], role)
            self.assertNotIn('password_hash', body['user'])
            self.adopt(body, headers)
            status, dashboard, _ = self.request('GET', '/api/dashboard')
            self.assertEqual((status,dashboard['role']), (200,role))
            token = self.cookie.split('=',1)[1]
            with connect(self.database) as db:
                row = db.execute('SELECT * FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row['is_demo'],0)

    def test_login_uses_registration_password_format_and_normalizes_email(self):
        status, body, _ = self.sign_in('  STUDENT@EXAMPLE.TEST  ')
        self.assertEqual(status, 200)
        self.assertEqual(body['user']['id'],2)
        self.assertTrue(auth.verify_password(self.password,self.encoded))

    def test_bad_unknown_inactive_and_passwordless_accounts_get_same_error(self):
        errors=[]
        for email, password in [('student@example.test','wrong'),('unknown@example.test',self.password),('outsider@example.test',self.password)]:
            status, body, headers = self.sign_in(email,password)
            self.assertEqual(status,401)
            self.assertNotIn('Set-Cookie',headers)
            errors.append(body)
        with connect(self.database) as db: db.execute('UPDATE users SET is_active=0 WHERE id=2')
        errors.append(self.sign_in()[1])
        self.assertTrue(all(error==errors[0] for error in errors))

    def test_invalid_input_is_rejected_before_password_work(self):
        with patch.object(auth,'verify_password') as verify:
            for data in [{}, {'email':[],'password':self.password}, {'email':'','password':'x'}, {'email':'x'*255,'password':'x'}, {'email':'student@example.test','password':'x'*129}, {'email':'\ud800','password':'x'}]:
                self.assertEqual(self.request('POST','/api/login',data)[0],400)
            verify.assert_not_called()

    def test_forged_role_and_user_id_do_not_change_the_account(self):
        status, body, _ = self.request('POST','/api/login',{'email':'student@example.test','password':self.password,'role':'administrator','user_id':3})
        self.assertEqual(status,200)
        self.assertEqual((body['user']['id'],body['user']['role']),(2,'student'))

    def test_login_replaces_previous_token_and_failure_keeps_valid_session(self):
        _, body, headers = self.sign_in(); self.adopt(body,headers); old=self.cookie
        self.assertEqual(self.sign_in(password='wrong')[0],401)
        self.assertEqual(self.request('GET','/api/session')[0],200)
        _, body, headers = self.sign_in(); self.adopt(body,headers)
        self.assertNotEqual(self.cookie,old)
        self.assertEqual(self.request('GET','/api/session',headers={'Cookie':old})[0],401)

    def test_cookie_flags_and_optional_https_secure_flag(self):
        _,_,headers=self.sign_in()
        for flag in ['HttpOnly','SameSite=Strict','Path=/','Max-Age=28800']:
            self.assertIn(flag,headers['Set-Cookie'])
        self.server.secure_cookies=True
        self.assertIn('; Secure',self.sign_in()[2]['Set-Cookie'])

    def test_cross_origin_and_non_json_login_are_rejected(self):
        for headers in [{'Origin':'https://evil.example'}, {'Origin':'http://127.0.0.1:8001'}, {'Origin':'null'}, {'Origin':'http://['}, {'Sec-Fetch-Site':'cross-site'}]:
            self.assertEqual(self.sign_in(headers=headers)[0],403)
        self.assertEqual(self.sign_in(headers={'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.sign_in(headers={'Origin':'http://127.0.0.1:8000','Sec-Fetch-Site':'same-origin'})[0],200)

    def test_logout_revokes_token_and_expires_cookie(self):
        _, body, headers = self.sign_in(); self.adopt(body,headers); old=self.cookie
        status, _, headers = self.request('POST','/api/logout',{})
        self.assertEqual(status,200)
        self.assertIn('Max-Age=0',headers['Set-Cookie'])
        self.assertEqual(self.request('GET','/api/session',headers={'Cookie':old})[0],401)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)

    def test_logout_requires_authentication_and_correct_csrf(self):
        self.assertEqual(self.request('POST','/api/logout',{})[0],401)
        _, body, headers = self.sign_in(); self.adopt(body,headers)
        self.assertEqual(self.request('POST','/api/logout',{},csrf=False)[0],403)
        self.assertEqual(self.request('GET','/api/session')[0],200)

    def test_login_and_logout_commit_before_sending_response(self):
        original=server.Handler.json; observed=[]
        def before_send(handler,status,data,extra=None):
            if status==200 and extra and 'Set-Cookie' in extra:
                with connect(self.database) as db: observed.append(db.execute('SELECT count(*) FROM sessions').fetchone()[0])
            return original(handler,status,data,extra)
        with patch.object(server.Handler,'json',before_send):
            _, body, headers = self.sign_in(); self.adopt(body,headers)
            self.request('POST','/api/logout',{})
        self.assertEqual(observed,[1,0])

    def test_password_change_during_verification_cannot_issue_session(self):
        def changed(password,stored):
            with connect(self.database) as db: db.execute("UPDATE users SET password_hash='changed' WHERE id=2")
            return True
        with patch.object(auth,'verify_password',changed):
            self.assertEqual(self.sign_in()[0],401)
        with connect(self.database) as db: self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)

    def test_demo_credential_login_is_not_real_authentication(self):
        self.server.demo=True
        self.assertEqual(self.sign_in()[0],409)
        self.server.demo=False
        self.assertEqual(self.request('POST','/api/demo/session',{'user_id':2})[0],404)
