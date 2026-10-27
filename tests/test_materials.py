"""Issue #12: authorized file access, ranges, headers and safe storage."""
import io
import json
import os
import stat
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import server
import test_access as access
from study_platform.db import connect
from study_platform.materials import CHUNK_SIZE, MaterialFile, initialize_storage
from study_platform.material_fixtures import seed_materials, sample_pdf, sample_png, sample_docx
from study_platform.security import create_session, COOKIE_NAME, PERMISSIONS


class MaterialTests(unittest.TestCase):
    request = access.AccessTests.request
    login_sample = access.AccessTests.login_sample
    tearDown = access.AccessTests.tearDown

    def setUp(self):
        access.AccessTests.setUp(self)
        self.storage = Path(self.temp.name) / 'files'
        initialize_storage(self.storage)
        self.server.storage = str(self.storage)
        with connect(self.database) as db:
            seed_materials(db, self.storage)
            self.ids = {row['stored_name']: row['id'] for row in db.execute('SELECT id,stored_name FROM materials')}
        self.public = self.ids['demo12-guide.pdf']
        self.private = self.ids['demo12-private.txt']

    def file(self, mid=None, action='view', method='GET', **options):
        return self.request(method, f'/api/materials/{mid or self.public}/{action}', **options)

    def catalog(self, query=''):
        return self.request('GET', '/api/materials' + query)

    def add(self, key, content, name='notes.txt', group=1, mime='text/plain'):
        (self.storage / key).write_bytes(content)
        with connect(self.database) as db:
            cursor = db.execute('''INSERT INTO materials(group_id,title,original_name,stored_name,content_type,size_bytes,uploaded_by)
                VALUES(?,'Extra material',?,?,?,?,1)''', (group, name, key, mime, len(content)))
            return cursor.lastrowid

    def test_anonymous_catalog_view_download_and_head_are_denied(self):
        self.assertEqual(self.catalog()[0], 401)
        for action in ['view', 'download']:
            self.assertEqual(self.file(action=action)[0], 401)
            self.assertEqual(self.file(action=action, method='HEAD')[0], 401)

    def test_catalog_is_group_scoped_and_contains_no_storage_or_session_secrets(self):
        for uid, total in [(1, 4), (2, 4), (3, 5), (4, 0)]:
            self.login_sample(uid)
            status, data, _ = self.catalog()
            self.assertEqual(status, 200)
            self.assertEqual(data['total'], total)
            if uid != 3:
                self.assertNotIn(self.private, [m['id'] for m in data['materials']])
                self.assertNotIn('Private Research', json.dumps(data))
            for secret in ['stored_name', 'password_hash', 'token_hash', 'csrf_token', str(self.storage)]:
                self.assertNotIn(secret, json.dumps(data))

    def test_group_filter_requires_access_and_does_not_trust_client_role(self):
        self.login_sample(2)
        status, data, _ = self.catalog('?group_id=2')
        self.assertEqual(status, 200)
        self.assertEqual({m['group_id'] for m in data['materials']}, {2})
        self.assertEqual(self.catalog('?group_id=3&role=administrator')[0], 403)
        self.assertEqual(self.catalog('?group_id=999')[0], 404)

    def test_pagination_and_validation(self):
        self.login_sample(2)
        _, first, _ = self.catalog('?limit=2&offset=0')
        _, second, _ = self.catalog('?limit=2&offset=2')
        self.assertEqual(first['total'], 4)
        self.assertEqual(len(first['materials']), 2)
        self.assertFalse({m['id'] for m in first['materials']} & {m['id'] for m in second['materials']})
        for query in ['?limit=0', '?limit=101', '?offset=-1', '?group_id=', '?group_id=1&group_id=2', '?offset=' + '9' * 100, '?' + '&'.join(f'x{i}=1' for i in range(21))]:
            self.assertEqual(self.catalog(query)[0], 400, query)

    def test_student_and_instructor_cannot_fetch_private_files_by_direct_url(self):
        for uid in [1, 2, 4]:
            self.login_sample(uid)
            for action in ['view', 'download']:
                self.assertEqual(self.file(self.private, action)[0], 403)
                self.assertEqual(self.file(self.private, action, method='HEAD')[0], 403)
        self.login_sample(3)
        self.assertEqual(self.file(self.private)[0], 200)

    def test_view_and_download_preserve_bytes_with_correct_dispositions(self):
        self.login_sample(2)
        status, view, headers = self.file()
        self.assertEqual(status, 200)
        self.assertEqual(view, sample_pdf())
        self.assertEqual(headers['Content-Type'], 'application/pdf')
        self.assertTrue(headers['Content-Disposition'].startswith('inline;'))
        status, saved, headers = self.file(action='download')
        self.assertEqual(status, 200)
        self.assertEqual(saved, view)
        self.assertTrue(headers['Content-Disposition'].startswith('attachment;'))
        self.assertIn('sprint-guide.pdf', headers['Content-Disposition'])
        self.assertEqual(headers['Cache-Control'], 'private, no-store')
        self.assertEqual(headers['Cross-Origin-Resource-Policy'], 'same-origin')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn('sandbox', headers['Content-Security-Policy'])

    def test_text_and_images_render_but_office_documents_are_download_only(self):
        self.login_sample(2)
        for key, mime, expected in [('demo12-policy.py', 'text/plain; charset=utf-8', None), ('demo12-image.png', 'image/png', sample_png()), ('demo12-handout.docx', 'application/octet-stream', sample_docx())]:
            status, body, headers = self.file(self.ids[key])
            self.assertEqual(status, 200)
            self.assertEqual(headers['Content-Type'], mime)
            self.assertTrue(headers['Content-Disposition'].startswith('attachment;' if 'docx' in key else 'inline;'))
            if expected is not None:
                self.assertEqual(body, expected)

    def test_active_html_svg_and_forged_mime_types_cannot_run_inline(self):
        self.login_sample(1)
        for key, name, content in [('active.html', 'active.html', b'<script>alert(1)</script>'), ('vector.svg', 'vector.svg', b'<svg onload="alert(1)"/>'), ('fake.png', 'fake.png', b'<script>not an image</script>'), ('fake.pdf', 'fake.pdf', b'not a pdf')]:
            mid = self.add(key, content, name, mime='text/html\r\nX-Forged: yes')
            status, _, headers = self.file(mid)
            self.assertEqual(status, 200)
            self.assertEqual(headers['Content-Type'], 'application/octet-stream')
            self.assertTrue(headers['Content-Disposition'].startswith('attachment;'))
            self.assertNotIn('X-Forged', headers)
        mid = self.add('safe.txt', b'<script>literal text</script>', 'safe.txt', mime='text/html')
        self.assertEqual(self.file(mid)[2]['Content-Type'], 'text/plain; charset=utf-8')

    def test_head_has_real_length_and_no_body_and_ignores_ranges(self):
        self.login_sample(2)
        status, body, headers = self.file(method='HEAD', headers={'Range': 'bytes=0-4'})
        self.assertEqual(status, 200)
        self.assertEqual(body, b'')
        self.assertEqual(int(headers['Content-Length']), len(sample_pdf()))
        self.assertNotIn('Content-Range', headers)

    def test_single_open_and_suffix_byte_ranges(self):
        self.login_sample(2)
        complete = sample_pdf()
        for value, expected in [('bytes=0-4', complete[:5]), ('bytes=5-', complete[5:]), ('bytes=-7', complete[-7:]), ('bytes=0-999999', complete), ('bytes=-' + '9' * 5000, complete)]:
            status, body, headers = self.file(headers={'Range': value})
            self.assertEqual(status, 206)
            self.assertEqual(body, expected)
            self.assertEqual(int(headers['Content-Length']), len(expected))
            self.assertIn(f'/{len(complete)}', headers['Content-Range'])

    def test_unsatisfiable_and_unsupported_ranges(self):
        self.login_sample(2)
        for value in ['bytes=999999-', 'bytes=4-2', 'bytes=-0', 'bytes=' + '9' * 5000 + '-']:
            status, body, headers = self.file(headers={'Range': value})
            self.assertEqual(status, 416)
            self.assertEqual(body, b'')
            self.assertEqual(headers['Content-Range'], f'bytes */{len(sample_pdf())}')
        for value in ['items=0-4', 'bytes=0-1,3-4', 'bytes=bad']:
            self.assertEqual(self.file(headers={'Range': value})[0], 200)
        self.assertEqual(self.file(headers={'Range': 'bytes=0-4', 'If-Range': '"unmatched"'})[0], 200)
        self.login_sample(2)
        self.assertEqual(self.file(self.private, headers={'Range': 'bytes=999999-'})[0], 403)

    def test_empty_files(self):
        self.login_sample(1)
        mid = self.add('empty.txt', b'')
        status, body, headers = self.file(mid)
        self.assertEqual((status, body, headers['Content-Length']), (200, b'', '0'))
        self.assertEqual(self.file(mid, headers={'Range': 'bytes=0-1'})[0], 416)

    def test_missing_and_incomplete_files_and_large_ids_are_handled(self):
        self.login_sample(1)
        self.assertEqual(self.file(99999)[0], 404)
        (self.storage / 'demo12-guide.pdf').unlink()
        self.assertEqual(self.file()[0], 404)
        mid = self.add('incomplete.txt', b'partial')
        with connect(self.database) as db:
            db.execute('UPDATE materials SET size_bytes=999 WHERE id=?', (mid,))
        self.assertEqual(self.file(mid)[0], 404)
        self.assertEqual(self.file('9' * 100)[0], 400)

    def test_traversal_and_absolute_storage_keys_are_rejected(self):
        self.login_sample(1)
        for key in ['../outside.txt', '/etc/passwd', '..\\outside.txt', 'nested/file.txt', '..', 'bad\x00name']:
            with connect(self.database) as db:
                db.execute('UPDATE materials SET stored_name=? WHERE id=?', (key, self.public))
            self.assertEqual(self.file()[0], 404, repr(key))

    def test_symlinks_and_replaced_storage_root_are_rejected(self):
        self.login_sample(1)
        original = self.storage / 'demo12-guide.pdf'
        original.unlink()
        target = Path(self.temp.name) / 'outside.pdf'; target.write_bytes(sample_pdf())
        original.symlink_to(target)
        self.assertEqual(self.file()[0], 404)
        original.unlink(); original.write_bytes(sample_pdf())
        moved = self.storage.with_name('moved'); self.storage.rename(moved)
        self.storage.symlink_to(moved, target_is_directory=True)
        self.assertEqual(self.file()[0], 404)

    def test_nonregular_files_and_insecure_storage_are_rejected(self):
        self.login_sample(1)
        original = self.storage / 'demo12-guide.pdf'; original.unlink(); original.mkdir()
        self.assertEqual(self.file()[0], 404)
        original.rmdir(); os.mkfifo(original, 0o600)
        self.assertEqual(self.file()[0], 404)
        os.chmod(self.storage, 0o755)
        with self.assertRaises(PermissionError):
            initialize_storage(self.storage)
        self.assertEqual(self.file()[0], 404)

    def test_download_names_cannot_include_path_or_control_header_injection(self):
        self.login_sample(1)
        with connect(self.database) as db:
            db.execute('UPDATE materials SET original_name=? WHERE id=?', ('../../café\r\nX-Bad: true.pdf', self.public))
        status, _, headers = self.file(action='download')
        self.assertEqual(status, 200)
        self.assertNotIn('X-Bad', headers)
        self.assertNotIn('../', headers['Content-Disposition'])
        self.assertIn('caf%C3%A9', headers['Content-Disposition'])
        self.assertNotIn('%0D', headers['Content-Disposition'])

    def test_streaming_uses_bounded_chunks(self):
        self.login_sample(1)
        content = b'x' * (CHUNK_SIZE * 3 + 25)
        mid = self.add('large.txt', content)
        calls = []; original = access.MemoryConnection.sendall
        def record(connection, data):
            calls.append(len(data)); return original(connection, data)
        with patch.object(access.MemoryConnection, 'sendall', record):
            status, body, _ = self.file(mid, action='download')
        self.assertEqual(status, 200)
        self.assertEqual(body, content)
        self.assertLessEqual(max(calls), CHUNK_SIZE)
        self.assertGreaterEqual(len(calls), 5)

    def test_transfer_failure_never_appends_a_json_error_to_file_bytes(self):
        self.login_sample(1)
        class Interrupted(io.BytesIO):
            def read(self, amount=-1):
                if self.tell():
                    raise OSError('Transfer interrupted')
                return super().read(min(amount, 4))
        @contextmanager
        def broken(*args, **kwargs):
            with Interrupted(b'abcdefgh') as stream:
                yield MaterialFile(stream, 8, 'text/plain', 'inline')
        raw = f'GET /api/materials/{self.public}/view HTTP/1.1\r\nHost: localhost\r\nCookie: {self.cookie}\r\nConnection: close\r\n\r\n'.encode()
        connection = access.MemoryConnection(raw)
        with patch.object(server, 'open_material', broken):
            handler = server.Handler(connection, ('127.0.0.1', 1234), self.server)
        output = connection.output.getvalue()
        self.assertEqual(output.count(b'HTTP/1.'), 1)
        self.assertNotIn(b'500', output.split(b'\r\n\r\n', 1)[1])
        self.assertTrue(handler.close_connection)

    def test_revocation_and_normal_mode_are_checked_for_every_file_request(self):
        self.login_sample(2)
        self.assertEqual(self.file()[0], 200)
        with connect(self.database) as db:
            db.execute('DELETE FROM memberships WHERE group_id=1 AND user_id=2')
        self.assertEqual(self.file()[0], 403)
        self.server.demo = False
        self.assertEqual(self.file()[0], 401)
        with connect(self.database) as db:
            token, _ = create_session(db, 3)
        self.cookie = f'{COOKIE_NAME}={token}'
        self.assertEqual(self.file(self.private)[0], 200)
        with patch.dict(PERMISSIONS, {'administrator': []}):
            self.assertEqual(self.file(self.private)[0], 403)

    def test_fixtures_are_idempotent_and_never_replace_conflicting_files(self):
        with connect(self.database) as db:
            seed_materials(db, self.storage)
            self.assertEqual(db.execute('SELECT count(*) FROM materials').fetchone()[0], 5)
        path = self.storage / 'demo12-guide.pdf'; path.write_bytes(b'Unrelated content')
        with self.assertRaises(ValueError):
            with connect(self.database) as db:
                seed_materials(db, self.storage)
        self.assertEqual(path.read_bytes(), b'Unrelated content')

    def test_fixture_files_and_directory_have_private_permissions(self):
        self.assertEqual(stat.S_IMODE(self.storage.stat().st_mode), 0o700)
        for path in self.storage.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_folder_creation_and_material_access_share_the_session_and_database(self):
        self.login_sample(1)
        status, data, _ = self.request('POST', '/api/groups/1/folders', {'name': 'Integration notes'})
        self.assertEqual(status, 201)
        folder_id = data['folder']['id']
        self.assertEqual(self.file()[0], 200)
        with connect(self.database) as db:
            from study_platform.db import initialize
            initialize(self.database)
            self.assertIsNotNone(db.execute('SELECT id FROM folders WHERE id=?', (folder_id,)).fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM materials').fetchone()[0], 5)
        self.login_sample(2)
        status, data, _ = self.request('GET', '/api/groups/1/folders')
        self.assertEqual(status, 200)
        self.assertIn(folder_id, [folder['id'] for folder in data['folders']])
        self.assertEqual(self.request('POST', '/api/groups/1/folders', {'name': 'Denied'})[0], 403)
        self.assertEqual(self.file(action='download')[0], 200)
        self.assertEqual(self.file(self.private)[0], 403)
        _, page, _ = self.request('GET', '/access')
        self.assertIn(b'id="folders-panel"', page)
        self.assertIn(b'href="/materials"', page)

    def test_library_assets_load(self):
        for path in ['/materials', '/materials/', '/materials.js', '/materials.css']:
            self.assertEqual(self.request('GET', path)[0], 200)
