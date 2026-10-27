"""Issue #7: permissions, validation, persistence and concurrent folder creation."""
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import test_access as access
from server import Handler
from study_platform.db import connect, initialize


class FolderTests(unittest.TestCase):
    setUp = access.AccessTests.setUp
    tearDown = access.AccessTests.tearDown
    request = access.AccessTests.request
    login_sample = access.AccessTests.login_sample

    def create(self, name, group_id=1, **options):
        return self.request('POST', f'/api/groups/{group_id}/folders', {'name': name}, **options)

    def test_anonymous_folder_and_group_requests_are_denied(self):
        self.assertEqual(self.request('GET', '/api/groups')[0], 401)
        self.assertEqual(self.request('GET', '/api/groups/1/folders')[0], 401)
        self.assertEqual(self.create('Notes')[0], 401)

    def test_group_picker_contains_only_authorized_groups(self):
        for uid, expected in [(1, {1, 2}), (2, {1, 2}), (3, {1, 2, 3}), (4, set())]:
            self.login_sample(uid)
            status, body, _ = self.request('GET', '/api/groups')
            self.assertEqual(status, 200)
            self.assertEqual({g['id'] for g in body['groups']}, expected)

    def test_owner_can_create_and_folder_survives_new_session_and_initialization(self):
        self.login_sample(1)
        status, data, _ = self.create('  Unit 1 notes  ')
        self.assertEqual(status, 201)
        folder = data['folder']
        self.assertEqual(folder['name'], 'Unit 1 notes')
        self.assertEqual(folder['group_id'], 1)
        self.assertEqual(folder['created_by'], 1)
        self.assertTrue(folder['created_at'])
        initialize(self.database)
        self.login_sample(1)
        status, data, _ = self.request('GET', '/api/groups/1/folders')
        self.assertEqual(status, 200)
        self.assertIn(folder['id'], [f['id'] for f in data['folders']])
        _, other, _ = self.request('GET', '/api/groups/2/folders')
        self.assertNotIn(folder['id'], [f['id'] for f in other['folders']])

    def test_student_can_list_but_cannot_create(self):
        self.login_sample(1)
        self.assertEqual(self.create('Shared notes')[0], 201)
        self.login_sample(2)
        status, data, _ = self.request('GET', '/api/groups/1/folders')
        self.assertEqual(status, 200)
        self.assertFalse(data['can_create'])
        self.assertEqual([f['name'] for f in data['folders']], ['Shared notes'])
        self.assertEqual(self.create('Student folder')[0], 403)

    def test_nonmember_cannot_read_or_create_private_group_folders(self):
        self.login_sample(4)
        self.assertEqual(self.request('GET', '/api/groups/1/folders')[0], 403)
        self.assertEqual(self.create('Nonmember folder')[0], 403)

    def test_instructor_membership_does_not_grant_another_groups_management(self):
        self.login_sample(1)
        with connect(self.database) as db:
            db.execute('INSERT INTO memberships VALUES(3,1)')
        status, data, _ = self.request('GET', '/api/groups/3/folders')
        self.assertEqual(status, 200)
        self.assertFalse(data['can_create'])
        self.assertEqual(self.create('Not my group', group_id=3)[0], 403)

    def test_administrator_can_create_in_any_existing_group(self):
        self.login_sample(3)
        for group_id in [1, 3]:
            status, data, _ = self.create('Administrator notes', group_id=group_id)
            self.assertEqual(status, 201)
            self.assertEqual(data['folder']['group_id'], group_id)

    def test_blank_long_nonstring_and_control_names_are_rejected(self):
        self.login_sample(1)
        for name in ['', '   ', 'x' * 81, None, 12, True, [], {}, 'bad\nname', 'bad\x7fname', 'hidden\u202ename']:
            with self.subTest(name=name):
                self.assertEqual(self.create(name)[0], 400)
        self.assertEqual(self.create('x' * 80)[0], 201)

    def test_duplicates_use_unicode_normalization_and_casefold_per_group(self):
        self.login_sample(1)
        self.assertEqual(self.create('Résumé')[0], 201)
        self.assertEqual(self.create('RE\u0301SUME\u0301')[0], 409)
        self.assertEqual(self.create('Straße')[0], 201)
        self.assertEqual(self.create('STRASSE')[0], 409)
        self.assertEqual(self.create('Résumé', group_id=2)[0], 201)

    def test_mutations_require_the_current_session_csrf_token(self):
        self.login_sample(1)
        self.assertEqual(self.create('No token', csrf=False)[0], 403)
        self.assertEqual(self.create('Wrong token', headers={'X-CSRF-Token': 'wrong'})[0], 403)
        self.assertEqual(self.create('Valid token')[0], 201)

    def test_missing_or_oversized_group_ids_are_handled(self):
        self.login_sample(1)
        self.assertEqual(self.create('No group', group_id=999)[0], 404)
        for group_id in ['9223372036854775808', '9' * 100]:
            self.assertEqual(self.create('Bad ID', group_id=group_id)[0], 400)
            self.assertEqual(self.request('GET', f'/api/groups/{group_id}/folders')[0], 400)

    def test_names_are_literal_data_and_foreign_keys_remain_enforced(self):
        self.login_sample(1)
        name = "<img src=x onerror=alert(1)>'); DROP TABLE users;--"
        self.assertEqual(self.create(name)[0], 201)
        _, data, _ = self.request('GET', '/api/groups/1/folders')
        self.assertEqual(data['folders'][0]['name'], name)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0], 4)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO folders(group_id,name,name_key,created_by) VALUES(999,'Bad','bad',1)")

    def test_creation_is_committed_before_success_is_sent(self):
        self.login_sample(1)
        original = Handler.json
        observed = []
        database = self.database
        def before_send(handler, status, data, extra=None):
            if status == 201 and 'folder' in data:
                with connect(database) as db:
                    observed.append(db.execute('SELECT 1 FROM folders WHERE id=?', (data['folder']['id'],)).fetchone() is not None)
            return original(handler, status, data, extra)
        with patch.object(Handler, 'json', before_send):
            self.assertEqual(self.create('Committed notes')[0], 201)
        self.assertEqual(observed, [True])

    def test_concurrent_duplicate_creation_keeps_one_folder(self):
        self.login_sample(1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda name: self.create(name)[0], ['Concurrent notes', 'CONCURRENT NOTES']))
        self.assertEqual(sorted(results), [201, 409])
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM folders').fetchone()[0], 1)

    def test_group_access_revocation_affects_the_next_folder_request(self):
        self.login_sample(2)
        self.assertEqual(self.request('GET', '/api/groups/1/folders')[0], 200)
        with connect(self.database) as db:
            db.execute('DELETE FROM memberships WHERE group_id=1 AND user_id=2')
        self.assertEqual(self.request('GET', '/api/groups/1/folders')[0], 403)

    def test_folder_browser_script_is_served(self):
        status, content, headers = self.request('GET', '/folders.js')
        self.assertEqual(status, 200)
        self.assertIn(b'StudyFolders', content)
        self.assertIn('javascript', headers['Content-Type'])


if __name__ == '__main__':
    unittest.main()
