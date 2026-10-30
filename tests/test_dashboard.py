"""Issue #6: scoped dashboard data, role-specific pages, and live summaries."""
import json
import unittest
from unittest.mock import patch
import server
import test_access as access
from study_platform.db import connect
from study_platform.security import create_session, COOKIE_NAME


class DashboardTests(unittest.TestCase):
    setUp = access.AccessTests.setUp
    tearDown = access.AccessTests.tearDown
    request = access.AccessTests.request
    login_sample = access.AccessTests.login_sample

    def dashboard(self, path='/api/dashboard'):
        status, data, _ = self.request('GET', path)
        self.assertEqual(status, 200)
        return data

    def test_anonymous_dashboard_data_and_role_pages_are_protected(self):
        for path in ['/api/dashboard', '/api/dashboard/administrator', '/dashboard/administrator', '/dashboard/student']:
            self.assertEqual(self.request('GET', path)[0], 401)

    def test_student_dashboard_has_learning_tools_and_only_visible_groups(self):
        self.login_sample(2)
        data = self.dashboard()
        self.assertEqual(data['role'], 'student')
        self.assertEqual({g['id'] for g in data['groups']}, {1, 2})
        self.assertEqual(data['summary'], {'groups': 2, 'study_partners': 1})
        self.assertIn('Learning tools', [n['label'] for n in data['navigation']])
        keys = {a['key'] for a in data['actions']}
        self.assertIn('quiz_attempts', keys)
        self.assertNotIn('quiz_creation', keys)
        self.assertNotIn('user_management', keys)
        self.assertTrue(all(not g['can_manage'] for g in data['groups']))

    def test_instructor_dashboard_has_teaching_tools_and_owned_group_counts(self):
        self.login_sample(1)
        data = self.dashboard()
        self.assertEqual(data['summary'], {'managed_groups': 2, 'shared_groups': 0})
        self.assertIn('Teaching tools', [n['label'] for n in data['navigation']])
        self.assertIn('quiz_creation', {a['key'] for a in data['actions']})
        self.assertNotIn('user_management', {a['key'] for a in data['actions']})
        self.assertTrue(all(g['can_manage'] for g in data['groups']))

    def test_admin_dashboard_has_global_summary_and_administration_tools(self):
        self.login_sample(3)
        data = self.dashboard()
        self.assertEqual(data['summary'], {'active_users': 4, 'groups': 3, 'memberships': 2})
        self.assertEqual({g['id'] for g in data['groups']}, {1, 2, 3})
        self.assertIn('Administration', [n['label'] for n in data['navigation']])
        self.assertIn('user_management', {a['key'] for a in data['actions']})
        self.assertTrue(all(g['can_manage'] for g in data['groups']))

    def test_role_pages_and_apis_cannot_be_used_to_impersonate_another_role(self):
        titles = set()
        for uid, role in [(1, 'instructor'), (2, 'student'), (3, 'administrator')]:
            self.login_sample(uid)
            titles.add(self.dashboard()['title'])
            for target in ['student', 'instructor', 'administrator']:
                expected = 200 if target == role else 403
                self.assertEqual(self.request('GET', f'/api/dashboard/{target}')[0], expected)
                self.assertEqual(self.request('GET', f'/dashboard/{target}')[0], expected)
        self.assertEqual(len(titles), 3)
        self.assertEqual(self.request('GET', '/api/dashboard/unknown')[0], 404)

    def test_client_supplied_role_or_user_id_cannot_expand_dashboard_scope(self):
        self.login_sample(2)
        data = self.dashboard('/api/dashboard?role=administrator&user_id=3')
        self.assertEqual(data['user']['id'], 2)
        self.assertEqual(data['role'], 'student')
        self.assertNotIn('active_users', data['summary'])
        self.assertNotIn(3, {g['id'] for g in data['groups']})

    def test_student_without_memberships_gets_an_empty_dashboard(self):
        self.login_sample(4)
        data = self.dashboard()
        self.assertEqual(data['groups'], [])
        self.assertEqual(data['summary'], {'groups': 0, 'study_partners': 0})
        self.assertNotIn('Private Research', json.dumps(data))

    def test_membership_revocation_is_reflected_by_the_next_refresh(self):
        self.login_sample(2)
        self.assertEqual(self.dashboard()['summary']['groups'], 2)
        with connect(self.database) as db:
            db.execute('DELETE FROM memberships WHERE group_id=1 AND user_id=2')
        data = self.dashboard()
        self.assertEqual([g['id'] for g in data['groups']], [2])
        self.assertEqual(data['summary']['groups'], 1)

    def test_active_account_summary_uses_database_state(self):
        self.login_sample(3)
        with connect(self.database) as db:
            db.execute('UPDATE users SET is_active=0 WHERE id=4')
        self.assertEqual(self.dashboard()['summary']['active_users'], 3)
        with connect(self.database) as db:
            db.execute("INSERT INTO users(id,name,email,role) VALUES(5,'New user','new@example.test','student')")
        self.assertEqual(self.dashboard()['summary']['active_users'], 4)

    def test_partner_counts_exclude_private_groups_and_inactive_users(self):
        self.login_sample(2)
        with connect(self.database) as db:
            db.execute("INSERT INTO users(id,name,email,role) VALUES(5,'Private user','private@example.test','student')")
            db.execute("INSERT INTO users(id,name,email,role,is_active) VALUES(6,'Inactive peer','inactive@example.test','student',0)")
            db.executemany('INSERT INTO memberships VALUES(?,?)', [(3, 5), (1, 6)])
        self.assertEqual(self.dashboard()['summary']['study_partners'], 1)
        with connect(self.database) as db:
            db.execute('UPDATE users SET is_active=1 WHERE id=6')
        self.assertEqual(self.dashboard()['summary']['study_partners'], 2)

    def test_joining_another_group_does_not_grant_instructor_management(self):
        self.login_sample(1)
        with connect(self.database) as db:
            db.execute('INSERT INTO memberships VALUES(3,1)')
        data = self.dashboard()
        self.assertEqual(data['summary'], {'managed_groups': 2, 'shared_groups': 1})
        self.assertFalse(next(g['can_manage'] for g in data['groups'] if g['id'] == 3))

    def test_profile_and_group_names_remain_data_without_session_secrets(self):
        self.login_sample(2)
        text = '<img src=x onerror=alert(1)>'
        with connect(self.database) as db:
            db.execute('UPDATE users SET name=?,password_hash=? WHERE id=2', (text, 'do-not-expose'))
            db.execute('UPDATE study_groups SET name=? WHERE id=1', (text,))
        data = self.dashboard()
        self.assertEqual(data['user']['name'], text)
        self.assertIn(text, [g['name'] for g in data['groups']])
        serialized = json.dumps(data)
        for secret in ['password_hash', 'do-not-expose', 'csrf_token', 'token_hash']:
            self.assertNotIn(secret, serialized)

    def test_upcoming_tools_have_no_broken_or_privileged_action_links(self):
        for uid in [1, 2, 3]:
            self.login_sample(uid)
            data = self.dashboard()
            for action in data['actions']:
                if not action['available']:
                    self.assertIsNone(action['href'])
                else:
                    self.assertIn(action['href'], ['#study-groups', '/access', '/access#folders-panel', '/materials', '/admin/users'])
            for key in ['quiz_attempts', 'results', 'quiz_creation', 'performance']:
                action = next((a for a in data['actions'] if a['key'] == key), None)
                if action:
                    self.assertFalse(action['available'])

    def test_optional_folder_integration_only_appears_when_capability_is_present(self):
        self.login_sample(1)
        data = self.dashboard()
        expected = callable(getattr(server, 'create_folder', None))
        self.assertEqual(next(a['available'] for a in data['actions'] if a['key'] == 'folders'), expected)
        with patch.object(server, 'create_folder', lambda: None, create=True):
            action = next(a for a in self.dashboard()['actions'] if a['key'] == 'folders')
        self.assertTrue(action['available'])
        self.assertEqual(action['href'], '/access#folders-panel')

    def test_material_workspace_is_linked_for_each_role_only_with_capability(self):
        for uid in [1, 2, 3]:
            self.login_sample(uid)
            action = next(a for a in self.dashboard()['actions'] if a['key'] == 'materials')
            self.assertTrue(action['available'])
            self.assertEqual(action['href'], '/materials')
            self.assertEqual(self.request('GET', action['href'])[0], 200)
        with patch.object(server, 'open_material', None):
            action = next(a for a in self.dashboard()['actions'] if a['key'] == 'materials')
            self.assertFalse(action['available'])
            self.assertIsNone(action['href'])
        with patch.dict(server.PERMISSIONS, {'administrator': ['dashboard']}):
            action = next(a for a in self.dashboard()['actions'] if a['key'] == 'materials')
            self.assertFalse(action['available'])
            self.assertIsNone(action['href'])

    def test_normal_mode_uses_real_issued_sessions_and_rejects_demo_sessions(self):
        self.login_sample(1)
        self.server.demo = False
        self.assertEqual(self.request('GET', '/api/dashboard')[0], 401)
        with connect(self.database) as db:
            token, _ = create_session(db, 1)
        self.cookie = f'{COOKIE_NAME}={token}'
        self.assertEqual(self.dashboard()['role'], 'instructor')
        with connect(self.database) as db:
            db.execute('UPDATE users SET is_active=0 WHERE id=1')
        self.assertEqual(self.request('GET', '/api/dashboard')[0], 401)

    def test_new_assets_and_old_access_workspace_remain_available(self):
        for path in ['/', '/dashboard', '/dashboard/', '/dashboard.js', '/dashboard.css', '/access']:
            self.assertEqual(self.request('GET', path)[0], 200)
        _, content, _ = self.request('GET', '/')
        self.assertIn(b'/dashboard.js', content)
        _, content, _ = self.request('GET', '/access')
        self.assertIn(b'/app.js', content)


    def test_user_management_link_is_admin_only_and_points_to_a_protected_page(self):
        for uid in [1, 2, 3]:
            self.login_sample(uid)
            action = next((a for a in self.dashboard()['actions'] if a['key'] == 'user_management'), None)
            if uid == 3:
                self.assertTrue(action['available'])
                self.assertEqual(action['href'], '/admin/users')
                self.assertEqual(self.request('GET', action['href'])[0], 200)
            else:
                self.assertIsNone(action)
                self.assertEqual(self.request('GET', '/admin/users')[0], 403)
