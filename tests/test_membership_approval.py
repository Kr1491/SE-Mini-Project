"""Restricted-group admission must be approved before it grants resource access."""
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import test_access as access
from study_platform.db import connect,initialize
from study_platform.materials import initialize_storage
from study_platform.material_fixtures import seed_materials
from study_platform.security import COOKIE_NAME,create_session


class MembershipApprovalTests(unittest.TestCase):
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
        self.sign_in(4)

    def sign_in(self,uid):
        with connect(self.database) as db:token,self.csrf=create_session(db,uid)
        self.cookie=f'{COOKIE_NAME}={token}'

    def join(self,gid=3):return self.request('POST',f'/api/groups/{gid}/join',{})
    def review(self,rid,decision='approve',**options):return self.request('POST',f'/api/membership-requests/{rid}/review',{'decision':decision},**options)

    def test_restricted_join_is_pending_and_does_not_grant_private_access(self):
        self.assertEqual(self.request('GET',f'/api/materials/{self.private_id}/view')[0],403)
        status,data,_=self.join()
        self.assertEqual(status,202);self.assertFalse(data['joined']);self.assertEqual(data['status'],'pending')
        self.assertNotIn('Private Research',str(data))
        self.assertEqual(self.request('GET',f'/api/materials/{self.private_id}/view')[0],403)
        self.assertEqual(self.request('GET','/api/groups/3/quizzes')[0],403)
        with connect(self.database) as db:self.assertIsNone(db.execute('SELECT 1 FROM memberships WHERE group_id=3 AND user_id=4').fetchone())

    def test_repeated_pending_join_creates_one_request(self):
        first=self.join()[1];second=self.join()[1]
        self.assertEqual(first['request_id'],second['request_id'])
        with connect(self.database) as db:self.assertEqual(db.execute('SELECT count(*) FROM membership_requests').fetchone()[0],1)

    def test_admin_approval_commits_membership_and_enables_next_request(self):
        rid=self.join()[1]['request_id'];student_cookie=self.cookie
        self.sign_in(3)
        self.assertEqual(self.review(rid)[0],200)
        self.assertTrue(self.review(rid)[1]['already_reviewed'])
        self.assertEqual(self.request('GET',f'/api/materials/{self.private_id}/view',headers={'Cookie':student_cookie})[0],200)
        with connect(self.database) as db:
            row=db.execute('SELECT status,reviewed_by,reviewed_at FROM membership_requests').fetchone()
            self.assertEqual(row['status'],'approved');self.assertEqual(row['reviewed_by'],3);self.assertTrue(row['reviewed_at'])
            self.assertEqual(db.execute('SELECT count(*) FROM memberships WHERE group_id=3 AND user_id=4').fetchone()[0],1)

    def test_other_instructor_and_students_cannot_approve_private_group(self):
        rid=self.join()[1]['request_id']
        self.assertEqual(self.review(rid)[0],403)
        self.sign_in(1)
        self.assertEqual(self.review(rid)[0],403)
        self.assertEqual(self.request('GET','/api/membership-requests')[1]['requests'],[])

    def test_group_owner_can_approve_restricted_teaching_group(self):
        with connect(self.database) as db:db.execute("UPDATE study_groups SET join_policy='approval' WHERE id=1")
        rid=self.join(1)[1]['request_id']
        self.sign_in(1)
        rows=self.request('GET','/api/membership-requests')[1]['requests']
        self.assertEqual(rows[0]['id'],rid)
        self.assertEqual(self.review(rid)[0],200)

    def test_rejection_does_not_grant_membership_and_reapplication_is_new_history(self):
        rid=self.join()[1]['request_id'];self.sign_in(3)
        self.assertEqual(self.review(rid,'reject')[0],200)
        self.assertEqual(self.review(rid,'approve')[0],409)
        self.sign_in(4)
        self.assertEqual(self.request('GET','/api/access/groups/3')[0],403)
        newer=self.join()[1]['request_id'];self.assertGreater(newer,rid)
        with connect(self.database) as db:self.assertEqual(db.execute('SELECT count(*) FROM membership_requests').fetchone()[0],2)

    def test_student_can_see_only_own_request_without_private_group_name(self):
        rid=self.join()[1]['request_id']
        status,data,_=self.request('GET','/api/membership-requests')
        self.assertEqual(status,200);self.assertFalse(data['can_review']);self.assertEqual(data['requests'][0]['id'],rid)
        self.assertIsNone(data['requests'][0]['group_name'])
        self.sign_in(2)
        self.assertEqual(self.request('GET','/api/membership-requests')[1]['requests'],[])

    def test_open_group_keeps_direct_idempotent_joining(self):
        self.assertEqual(self.join(1)[0],201)
        status,data,_=self.join(1)
        self.assertEqual(status,200);self.assertTrue(data['already_member'])

    def test_review_requires_csrf_and_valid_decision(self):
        rid=self.join()[1]['request_id'];self.sign_in(3)
        self.assertEqual(self.review(rid,csrf=False)[0],403)
        self.assertEqual(self.review(rid,'maybe')[0],400)
        self.assertEqual(self.review(999)[0],404)

    def test_inactive_requester_is_not_approved(self):
        rid=self.join()[1]['request_id'];self.sign_in(3)
        with connect(self.database) as db:db.execute('UPDATE users SET is_active=0 WHERE id=4')
        self.assertEqual(self.review(rid)[0],409)
        self.assertEqual(self.review(rid,'reject')[0],200)

    def test_two_reviewers_cannot_overwrite_each_others_decision(self):
        rid=self.join()[1]['request_id'];self.sign_in(3)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda decision:self.review(rid,decision)[0],['approve','reject']))
        self.assertEqual(sorted(results),[200,409])
        with connect(self.database) as db:
            decision=db.execute('SELECT status FROM membership_requests WHERE id=?',(rid,)).fetchone()[0]
            count=db.execute('SELECT count(*) FROM memberships WHERE group_id=3 AND user_id=4').fetchone()[0]
            self.assertEqual(count,1 if decision=='approved' else 0)

    def test_new_groups_default_to_approval_and_can_explicitly_allow_open_joining(self):
        self.sign_in(1)
        status,data,_=self.request('POST','/api/groups',{'name':'Restricted class'})
        self.assertEqual(status,201);self.assertEqual(data['group']['join_policy'],'approval')
        self.assertEqual(self.request('POST','/api/groups',{'name':'Bad policy','join_policy':'anything'})[0],400)
        status,data,_=self.request('POST','/api/groups',{'name':'Open class','join_policy':'open'})
        self.sign_in(4);self.assertEqual(self.join(data['group']['id'])[0],201)

    def test_demo_memberships_are_read_only(self):
        self.server.demo=True
        self.assertEqual(self.join()[0],409)
        self.assertTrue(self.request('GET','/api/membership-requests')[1]['read_only'])

    def test_legacy_groups_migrate_to_approval_without_losing_group_data(self):
        path=Path(self.temp.name)/'legacy.db'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,email TEXT,password_hash TEXT,role TEXT,is_active INTEGER)')
            db.execute("INSERT INTO users VALUES(1,'Owner','owner@example.test',NULL,'instructor',1)")
            db.execute('CREATE TABLE study_groups(id INTEGER PRIMARY KEY,name TEXT,created_by INTEGER REFERENCES users(id))')
            db.execute("INSERT INTO study_groups VALUES(9,'Existing class',1)")
        initialize(path);initialize(path)
        with connect(path) as db:
            row=db.execute('SELECT * FROM study_groups WHERE id=9').fetchone()
            self.assertEqual((row['name'],row['created_by'],row['join_policy']),('Existing class',1,'approval'))


    def test_old_approved_request_cannot_restore_revoked_membership(self):
        rid=self.join()[1]['request_id'];self.sign_in(3);self.assertEqual(self.review(rid)[0],200)
        with connect(self.database) as db:db.execute('DELETE FROM memberships WHERE group_id=3 AND user_id=4')
        self.assertTrue(self.review(rid)[1]['already_reviewed'])
        self.sign_in(4);self.assertEqual(self.request('GET',f'/api/materials/{self.private_id}/view')[0],403)
        self.assertGreater(self.join()[1]['request_id'],rid)
