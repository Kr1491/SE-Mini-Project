"""Issue #18: authorization, account updates, revocation and concurrency."""
import json
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import server
import test_access as access
from study_platform.admin_users import update_user_access
from study_platform.db import connect, initialize
from study_platform.security import APIError, COOKIE_NAME, create_session


class AdminUserTests(unittest.TestCase):
    request = access.AccessTests.request
    tearDown = access.AccessTests.tearDown

    def setUp(self):
        access.AccessTests.setUp(self)
        self.server.demo = False
        self.sign_in(3)

    def sign_in(self, uid):
        with connect(self.database) as db:
            token, self.csrf = create_session(db, uid)
        self.cookie = f'{COOKIE_NAME}={token}'
        return self.cookie, self.csrf

    def update(self, uid=2, **changes):
        data = {'role': 'instructor', 'is_active': True, 'version': 0, **changes}
        return self.request('POST', f'/api/admin/users/{uid}', data)

    def listing(self, query=''):
        return self.request('GET', '/api/admin/users' + query)

    def test_unauthenticated_requests_to_page_list_and_update_are_denied(self):
        self.cookie = ''
        for method,path,data in [('GET','/admin/users',None),('GET','/api/admin/users',None),('POST','/api/admin/users/2',{'role':'administrator','is_active':True,'version':0})]:
            self.assertEqual(self.request(method,path,data)[0],401)

    def test_students_and_instructors_cannot_read_or_mutate_admin_data(self):
        for uid in [1,2,4]:
            self.sign_in(uid)
            self.assertEqual(self.request('GET','/admin/users')[0],403)
            self.assertEqual(self.listing()[0],403)
            self.assertEqual(self.listing('?limit=bad')[0],403)
            self.assertEqual(self.update()[0],403)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM user_access_audit').fetchone()[0],0)

    def test_admin_listing_is_paginated_and_excludes_passwords_and_sessions(self):
        status,data,_=self.listing('?limit=2')
        self.assertEqual(status,200)
        self.assertEqual((data['total'],len(data['users'])),(4,2))
        _,second,_=self.listing('?limit=2&offset=2')
        self.assertFalse({u['id'] for u in data['users']} & {u['id'] for u in second['users']})
        for secret in ['password_hash','token_hash','csrf_token',self.cookie.split('=',1)[1]]:
            self.assertNotIn(secret,json.dumps(data))
        self.assertEqual({r['value'] for r in data['roles']},{'student','instructor','administrator'})
        _,all_rows,_=self.listing()
        self.assertTrue(next(u for u in all_rows['users'] if u['id']==3)['is_you'])

    def test_role_access_and_literal_search_filters(self):
        self.assertEqual(self.listing('?role=student')[1]['total'],2)
        self.assertEqual(self.listing('?q=student%40example.test')[1]['total'],1)
        self.assertEqual(self.listing('?q=%25')[1]['total'],0)
        self.assertEqual(self.listing('?q=%27%20OR%201%3D1--')[1]['total'],0)
        self.update(is_active=False,role='student')
        self.assertEqual(self.listing('?access=inactive')[1]['total'],1)
        self.assertEqual(self.listing('?access=active')[1]['total'],3)

    def test_bad_queries_and_oversized_ids_are_bad_requests(self):
        for query in ['?limit=0','?limit=51','?offset=-1','?role=root','?access=maybe','?q='+('x'*101),'?limit=1&limit=2','?offset='+('9'*5000)]:
            self.assertEqual(self.listing(query)[0],400,query)
        self.assertEqual(self.request('POST','/api/admin/users/'+'9'*100,{'role':'student','is_active':True,'version':0})[0],400)

    def test_role_change_persists_and_records_actor_and_previous_state(self):
        status,data,_=self.update()
        self.assertEqual(status,200)
        self.assertEqual((data['user']['role'],data['user']['version']),('instructor',1))
        initialize(self.database)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT role FROM users WHERE id=2').fetchone()[0],'instructor')
            row=db.execute('SELECT * FROM user_access_audit').fetchone()
            self.assertEqual((row['actor_id'],row['user_id'],row['old_role'],row['new_role']),(3,2,'student','instructor'))
            self.assertTrue(row['changed_at'])

    def test_role_changes_revoke_existing_tokens_and_new_login_gets_new_permissions(self):
        old,_=self.sign_in(2)
        self.sign_in(3)
        self.assertEqual(self.update()[0],200)
        self.assertEqual(self.request('GET','/api/session',headers={'Cookie':old})[0],401)
        self.sign_in(2)
        status,data,_=self.request('GET','/api/session')
        self.assertEqual(status,200)
        self.assertEqual(data['user']['role'],'instructor')
        self.assertIn('quiz.create',data['permissions'])
        self.assertEqual(self.request('GET','/api/admin/users')[0],403)

    def test_suspension_and_reactivation_do_not_restore_old_sessions(self):
        old,_=self.sign_in(2)
        self.sign_in(3)
        self.assertEqual(self.update(role='student',is_active=False)[0],200)
        self.assertEqual(self.request('GET','/api/session',headers={'Cookie':old})[0],401)
        self.assertEqual(self.update(role='student',is_active=True,version=1)[0],200)
        self.assertEqual(self.request('GET','/api/session',headers={'Cookie':old})[0],401)
        self.sign_in(2)
        self.assertEqual(self.request('GET','/api/session')[0],200)

    def test_self_demotion_and_suspension_are_blocked(self):
        self.assertEqual(self.update(3,role='student')[0],409)
        self.assertEqual(self.update(3,role='administrator',is_active=False)[0],409)
        with connect(self.database) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users WHERE role='administrator' AND is_active=1").fetchone()[0],1)

    def test_stale_versions_do_not_overwrite_saved_changes(self):
        self.assertEqual(self.update()[0],200)
        self.assertEqual(self.update(role='student')[0],409)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT role,access_version FROM users WHERE id=2').fetchone()[:],('instructor',1))
            self.assertEqual(db.execute('SELECT count(*) FROM user_access_audit').fetchone()[0],1)

    def test_noop_does_not_audit_revoke_or_increment_version(self):
        old,_=self.sign_in(2);self.sign_in(3)
        status,data,_=self.update(role='student')
        self.assertEqual(status,200);self.assertFalse(data['changed'])
        self.assertEqual(self.request('GET','/api/session',headers={'Cookie':old})[0],200)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT access_version FROM users WHERE id=2').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM user_access_audit').fetchone()[0],0)

    def test_csrf_and_payload_validation_prevent_mass_assignment(self):
        payload={'role':'instructor','is_active':True,'version':0}
        self.assertEqual(self.request('POST','/api/admin/users/2',payload,csrf=False)[0],403)
        self.assertEqual(self.request('POST','/api/admin/users/2',payload,headers={'X-CSRF-Token':'wrong'})[0],403)
        for changes in [{'role':'root'},{'role':[]},{'is_active':1},{'version':True},{'version':-1},{'password_hash':'bad'},{'id':3}]:
            self.assertEqual(self.request('POST','/api/admin/users/2',{**payload,**changes})[0],400)
        self.assertEqual(self.request('POST','/api/admin/users/2',{})[0],400)
        self.assertEqual(self.update(999)[0],404)

    def test_pending_authority_is_rechecked_inside_the_write_transaction(self):
        actor={'id':3,'role':'administrator'}
        with connect(self.database) as db:db.execute("UPDATE users SET role='student' WHERE id=3")
        with self.assertRaises(APIError) as caught:
            with connect(self.database) as db:update_user_access(db,actor,2,{'role':'instructor','is_active':True,'version':0})
        self.assertEqual(caught.exception.status,403)

    def test_concurrent_admin_demotion_preserves_one_administrator(self):
        with connect(self.database) as db:
            db.execute("INSERT INTO users(id,name,email,role) VALUES(5,'Second Admin','second@example.test','administrator')")
        def change(pair):
            actor,target=pair
            try:
                with connect(self.database) as db:update_user_access(db,{'id':actor},target,{'role':'student','is_active':True,'version':0})
                return 200
            except APIError as exc:return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(change,[(3,5),(5,3)]))
        self.assertEqual(sorted(results),[200,403])
        with connect(self.database) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users WHERE role='administrator' AND is_active=1").fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM user_access_audit').fetchone()[0],1)

    def test_audit_failure_rolls_back_role_change_and_session_deletion(self):
        old,_=self.sign_in(2);self.sign_in(3)
        with connect(self.database) as db:
            db.execute("CREATE TRIGGER deny_test_audit BEFORE INSERT ON user_access_audit BEGIN SELECT RAISE(ABORT,'audit test failure'); END")
        self.assertEqual(self.update()[0],500)
        self.assertEqual(self.request('GET','/api/session',headers={'Cookie':old})[0],200)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT role,access_version FROM users WHERE id=2').fetchone()[:],('student',0))

    def test_commit_precedes_success_response(self):
        original=server.Handler.json;observed=[]
        def before_send(handler,status,data,extra=None):
            if status==200 and data.get('changed'):
                with connect(self.database) as db:observed.append(db.execute('SELECT role FROM users WHERE id=2').fetchone()[0])
            return original(handler,status,data,extra)
        with patch.object(server.Handler,'json',before_send):self.assertEqual(self.update()[0],200)
        self.assertEqual(observed,['instructor'])

    def test_demo_records_are_read_only_and_not_corrupted(self):
        self.server.demo=True
        status,data,_=self.listing()
        self.assertEqual(status,200);self.assertTrue(data['read_only'])
        self.assertEqual(self.update()[0],409)
        from study_platform.demo import validate_demo
        with connect(self.database) as db:validate_demo(db)

    def test_existing_database_adds_version_without_losing_account_data(self):
        path=Path(self.temp.name)/'old-users.db'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,email TEXT,password_hash TEXT,role TEXT,is_active INTEGER)')
            db.execute("INSERT INTO users VALUES(9,'Existing','old@example.test','preserved','student',1)")
        initialize(path);initialize(path)
        with connect(path) as db:
            row=db.execute('SELECT * FROM users WHERE id=9').fetchone()
            self.assertEqual((row['name'],row['password_hash'],row['access_version']),('Existing','preserved',0))
