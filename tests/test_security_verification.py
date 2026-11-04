"""Issue #21: local security verification including results and performance."""
import json
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import server
import test_access as access
from study_platform.db import connect,initialize
from study_platform.materials import initialize_storage
from study_platform.material_fixtures import seed_materials
from study_platform.recovery import create_backup,restore_backup,validate_backup
from study_platform.security import COOKIE_NAME,create_session


class EndpointSecurityTests(unittest.TestCase):
    request=access.AccessTests.request
    tearDown=access.AccessTests.tearDown

    def setUp(self):
        access.AccessTests.setUp(self)
        self.server.demo=False
        self.storage=Path(self.temp.name)/'files';initialize_storage(self.storage)
        self.server.storage=str(self.storage)
        with connect(self.database) as db:
            seed_materials(db,self.storage)
            self.private_id=db.execute("SELECT id FROM materials WHERE stored_name='demo12-private.txt'").fetchone()[0]

    def sign_in(self,uid):
        with connect(self.database) as db:token,self.csrf=create_session(db,uid)
        self.cookie=f'{COOKIE_NAME}={token}'

    def test_anonymous_protected_endpoint_matrix(self):
        cases=[('GET','/api/session',None),('GET','/api/dashboard',None),('GET','/api/groups',None),
            ('GET','/api/groups/1/folders',None),('GET','/api/materials',None),('GET','/api/materials/1/view',None),
            ('GET','/api/materials/1/download',None),('GET','/api/groups/1/materials',None),('GET','/api/groups/1/quizzes',None),
            ('GET','/api/admin/users',None),('GET','/admin/users',None),('GET','/api/membership-requests',None),
            ('GET','/api/results/me',None),('GET','/api/groups/1/results',None),
            ('GET','/api/quiz-attempts/1/result',None),('POST','/api/quizzes/1/publish',{}),
            ('POST','/api/quizzes/1/attempts',{}),('POST','/api/quiz-attempts/1/submit',{'answers':[]}),
            ('POST','/api/membership-requests/1/review',{'decision':'approve'}),('POST','/api/groups',{'name':'blocked'}),
            ('POST','/api/groups/1/folders',{'name':'blocked'}),('POST','/api/groups/1/quizzes',{}),
            ('POST','/api/groups/1/join',{}),('POST','/api/admin/users/2',{}),('POST','/api/logout',{})]
        for method,path,data in cases:
            with self.subTest(method=method,path=path):self.assertEqual(self.request(method,path,data)[0],401)
        self.assertEqual(self.request('HEAD',f'/api/materials/{self.private_id}/download')[0],401)

    def test_student_cannot_use_authoring_or_administration_actions(self):
        self.sign_in(2)
        for method,path,data in [('GET','/api/access/instructor',None),('GET','/api/access/admin',None),
            ('GET','/api/access/quiz-create',None),('GET','/api/dashboard/administrator',None),
            ('GET','/api/admin/users',None),('GET','/admin/users',None),('GET','/api/groups/1/results',None),
            ('POST','/api/quizzes/1/publish',{}),

            ('POST','/api/membership-requests/1/review',{'decision':'approve'}),('POST','/api/groups',{'name':'blocked'}),
            ('POST','/api/groups/1/folders',{'name':'blocked'}),('POST','/api/groups/1/quizzes',{}),
            ('POST','/api/admin/users/3',{'role':'student','is_active':False,'version':0})]:
            with self.subTest(path=path):self.assertEqual(self.request(method,path,data)[0],403)

    def test_instructor_is_scoped_to_permitted_groups(self):
        self.sign_in(1)
        for path in ['/api/admin/users','/api/groups/3/folders','/api/groups/3/quizzes','/api/groups/3/materials','/api/groups/3/results',
                     f'/api/materials/{self.private_id}/view',f'/api/materials/{self.private_id}/download']:
            self.assertEqual(self.request('GET',path)[0],403,path)
        self.assertEqual(self.request('GET','/api/groups/1/folders')[0],200)

    def test_nonmember_direct_reads_do_not_disclose_group_content(self):
        self.sign_in(4)
        for path in ['/api/groups/1/folders','/api/groups/1/quizzes','/api/groups/1/materials',
                     f'/api/materials/{self.private_id}/view',f'/api/materials/{self.private_id}/download']:
            self.assertEqual(self.request('GET',path)[0],403,path)
        _,data,_=self.request('GET','/api/materials')
        self.assertEqual(data['materials'],[])

    def test_student_responses_omit_passwords_session_hashes_and_correct_flags(self):
        self.sign_in(1)
        quiz={'title':'Security quiz','questions':[{'question':'Pick one','options':[{'text':'A','is_correct':True},{'text':'B','is_correct':False}]}]}
        status,created,_=self.request('POST','/api/groups/1/quizzes',quiz)
        self.assertEqual(status,201)
        self.assertEqual(self.request('POST',f"/api/quizzes/{created['quiz']['id']}/publish",{})[0],200)
        with connect(self.database) as db:db.execute("UPDATE users SET password_hash='PRIVATE_PASSWORD_SENTINEL' WHERE id=2")
        self.sign_in(2)
        for path in ['/api/session','/api/dashboard','/api/groups','/api/materials','/api/groups/1/quizzes']:
            status,data,headers=self.request('GET',path)
            self.assertEqual(status,200,path)
            if path=='/api/groups/1/quizzes':
                self.assertEqual(len(data['quizzes']),1)
                self.assertGreater(len(data['quizzes'][0]['questions']),0)
            serialized=json.dumps(data)
            for secret in ['password_hash','token_hash','PRIVATE_PASSWORD_SENTINEL','is_correct']:
                self.assertNotIn(secret,serialized,path)
            self.assertIn('no-store',headers['Cache-Control'])
            self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        # The current account's CSRF token is deliberately available to its UI;
        # it is not a password or somebody else's session/answer key.

    def test_state_changes_reject_missing_csrf_and_inactive_sessions(self):
        self.sign_in(1)
        self.assertEqual(self.request('POST','/api/groups/1/folders',{'name':'blocked'},csrf=False)[0],403)
        with connect(self.database) as db:db.execute('UPDATE users SET is_active=0 WHERE id=1')
        self.assertEqual(self.request('GET','/api/dashboard')[0],401)
        self.assertEqual(self.request('POST','/api/groups/1/folders',{'name':'blocked'})[0],401)

    def test_secure_cookie_option_is_present_but_does_not_prove_deployed_tls(self):
        self.server.demo=True;self.server.secure_cookies=True
        status,_,headers=self.request('POST','/api/demo/session',{'user_id':2})
        self.assertEqual(status,200)
        for flag in ['HttpOnly','SameSite=Strict','; Secure']:
            self.assertIn(flag,headers['Set-Cookie'])


    def test_saved_quiz_receipt_hides_keys_and_rejects_other_student(self):
        self.sign_in(1)
        quiz={'title':'Receipt privacy','questions':[{'question':'Pick one','options':[{'text':'A','is_correct':True},{'text':'B','is_correct':False}]}]}
        _,created,_=self.request('POST','/api/groups/1/quizzes',quiz)
        qid=created['quiz']['id']
        self.assertEqual(self.request('POST',f'/api/quizzes/{qid}/publish',{})[0],200)
        self.sign_in(2)
        _,started,_=self.request('POST',f'/api/quizzes/{qid}/attempts',{})
        attempt=started['attempt_id'];question=started['quiz']['questions'][0]
        status,data,_=self.request('POST',f'/api/quiz-attempts/{attempt}/submit',{'answers':[{'question_id':question['id'],'option_id':question['options'][0]['id']}],'score':999,'student_id':4})
        self.assertEqual(status,200);self.assertEqual(data['result']['score'],1);self.assertEqual(data['student_id'],2)
        receipt=self.request('GET',f'/api/quiz-attempts/{attempt}/result')[1]
        status,history,headers=self.request('GET','/api/results/me')
        self.assertEqual(status,200);self.assertEqual(history['results'][0]['score'],1)
        self.assertIn('no-store',headers['Cache-Control'])
        for secret in ['grading_snapshot','correct_option_id','is_correct','password_hash','token_hash']:
            self.assertNotIn(secret,json.dumps(receipt))
            self.assertNotIn(secret,json.dumps(started))
            self.assertNotIn(secret,json.dumps(history))
        self.sign_in(4)
        self.assertEqual(self.request('GET',f'/api/quiz-attempts/{attempt}/result')[0],404)
        self.assertEqual(self.request('GET','/api/results/me?student_id=2')[1]['results'],[])
        self.sign_in(1)
        status,performance,headers=self.request('GET','/api/groups/1/results')
        self.assertEqual(status,200);self.assertEqual(performance['results'][0]['student_id'],2)
        self.assertIn('no-store',headers['Cache-Control'])
        for secret in ['grading_snapshot','correct_option_id','is_correct','password_hash','token_hash']:
            self.assertNotIn(secret,json.dumps(performance))

    def test_passwordless_accounts_cannot_authenticate_with_the_dummy_check_password(self):
        status,_,headers=self.request('POST','/api/login',{'email':'student@example.test','password':'not-a-real-account'})
        self.assertEqual(status,401);self.assertNotIn('Set-Cookie',headers)

    def test_registration_helper_uses_salted_password_hashes_and_safe_output(self):
        from study_platform.auth import register_user,verify_password
        password='Security audit test password 42!'
        with connect(self.database) as db:
            first=register_user(db,{'name':'Audit Student','email':'audit-one@example.test','password':password})
            second=register_user(db,{'name':'Audit Student','email':'audit-two@example.test','password':password})
            rows=[db.execute('SELECT password_hash FROM users WHERE id=?',(account['id'],)).fetchone()[0] for account in [first,second]]
            self.assertNotEqual(rows[0],rows[1])
            for encoded in rows:
                self.assertTrue(encoded.startswith('pbkdf2_sha256$600000$'))
                self.assertNotIn(password,encoded)
                self.assertTrue(verify_password(password,encoded))
        self.assertNotIn('password_hash',first);self.assertNotIn('password',first)
        self.assertNotIn(password,json.dumps(first))


    def test_folder_write_rechecks_stale_role_context(self):
        from study_platform.folders import create_folder
        from study_platform.security import APIError
        with connect(self.database) as db:db.execute("UPDATE users SET role='student' WHERE id=1")
        with self.assertRaises(APIError) as caught:
            with connect(self.database) as db:create_folder(db,{'id':1,'role':'instructor'},1,'Stale folder')
        self.assertEqual(caught.exception.status,403)

    def test_mid_request_revocation_blocks_group_folder_and_upload_writes(self):
        from study_platform.admin_users import update_user_access
        original=server.current_session
        boundary='security-boundary'
        raw=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="stale.txt"\r\nContent-Type: text/plain\r\n\r\nstale write\r\n--{boundary}--\r\n').encode()
        for path,data,options in [('/api/groups',{'name':'Stale group'},{}),('/api/groups/1/folders',{'name':'Stale folder'},{}),('/api/groups/1/materials',None,{'raw':raw,'headers':{'Content-Type':'multipart/form-data; boundary='+boundary}})]:
            with connect(self.database) as db:db.execute("UPDATE users SET role='instructor',is_active=1 WHERE id=1")
            self.sign_in(1)
            fired=[]
            def revoke_after_auth(db,cookie,**kwargs):
                account=original(db,cookie,**kwargs)
                if not fired:
                    fired.append(True)
                    with connect(self.database) as separate:
                        version=separate.execute('SELECT access_version FROM users WHERE id=1').fetchone()[0]
                        update_user_access(separate,{'id':3},1,{'role':'student','is_active':True,'version':version})
                return account
            with patch.object(server,'current_session',revoke_after_auth):
                self.assertIn(self.request('POST',path,data,**options)[0],[401,403],path)


class BackupSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name);self.database=self.root/'app.db'
        initialize(self.database)
        self.storage=self.root/'files';self.storage.mkdir(mode=0o700)
        (self.storage/'notes.txt').write_text('Academic notes')
        self.output=self.root/'backups'

    def tearDown(self):self.temp.cleanup()

    def test_backup_rejects_storage_symlink_without_copying_its_target(self):
        secret=self.root/'secret.txt';secret.write_text('OUTSIDE_STORAGE_SECRET')
        (self.storage/'link.txt').symlink_to(secret)
        with self.assertRaises(ValueError):create_backup(self.database,self.storage,self.output)
        self.assertFalse(list(self.output.glob('backup-*')))

    def test_backup_rejects_symlink_storage_root_and_database(self):
        linked=self.root/'linked-files';linked.symlink_to(self.storage,target_is_directory=True)
        with self.assertRaises(ValueError):create_backup(self.database,linked,self.output)
        linked_db=self.root/'linked.db';linked_db.symlink_to(self.database)
        with self.assertRaises(ValueError):create_backup(linked_db,self.storage,self.output)

    @unittest.skipUnless(os.name=='posix','POSIX owner-only permission requirement')
    def test_backup_and_restored_data_have_private_permissions(self):
        previous=os.umask(0o022)
        try:
            backup=create_backup(self.database,self.storage,self.output)
            target=self.root/'restored';target.mkdir(mode=0o700)
            restore_backup(backup,target/'accounts.db',target/'files')
        finally:os.umask(previous)
        for path in [self.output,backup,backup/'storage',target/'files']:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o700,path)
        for path in [backup/'database.sqlite3',backup/'manifest.json',backup/'storage/notes.txt',target/'accounts.db',target/'files/notes.txt']:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600,path)

    @unittest.skipUnless(os.name=='posix','POSIX owner-only permission requirement')
    def test_restore_refuses_shared_destination_without_changing_existing_data(self):
        backup=create_backup(self.database,self.storage,self.output)
        target=self.root/'shared';target.mkdir(mode=0o755)
        existing=target/'app.db';existing.write_text('KEEP_EXISTING')
        with self.assertRaises(PermissionError):restore_backup(backup,existing,target/'files')
        self.assertEqual(existing.read_text(),'KEEP_EXISTING')

    def test_backup_validation_rejects_symlink_components(self):
        backup=create_backup(self.database,self.storage,self.output)
        original=backup/'database.sqlite3';outside=self.root/'saved.sqlite3';original.rename(outside);original.symlink_to(outside)
        with self.assertRaises(ValueError):validate_backup(backup)
