import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from email.message import EmailMessage

from server import Handler, MAX_UPLOAD_BYTES, ALLOWED_EXTENSIONS
from study_platform.db import connect, initialize
from study_platform.demo import seed
from tests.test_access import MemoryConnection


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / 'test.db'
        self.upload_dir = self.root / 'uploads'
        initialize(self.database)
        with connect(self.database) as db:
            seed(db)
        self.server = SimpleNamespace(
            database=self.database, demo=True, upload_dir=self.upload_dir
        )
        self.cookie = ''
        self.csrf = ''

    def tearDown(self):
        self.temp.cleanup()

    def request(self, method, path, body=b'', content_type=None, extra_headers=None):
        headers = {
            'Host': '127.0.0.1:8000',
            'Connection': 'close',
            'Cookie': self.cookie,
            'X-CSRF-Token': self.csrf,
            'Content-Length': str(len(body)),
        }
        if content_type:
            headers['Content-Type'] = content_type
        if extra_headers:
            headers.update(extra_headers)
        raw = (
            f'{method} {path} HTTP/1.1\r\n'
            + ''.join(f'{k}: {v}\r\n' for k, v in headers.items())
            + '\r\n'
        ).encode() + body
        connection = MemoryConnection(raw)
        Handler(connection, ('127.0.0.1', 12345), self.server)
        head, content = connection.output.getvalue().split(b'\r\n\r\n', 1)
        lines = head.decode().split('\r\n')
        status = int(lines[0].split()[1])
        response_headers = dict(line.split(': ', 1) for line in lines[1:])
        if response_headers.get('Content-Type', '').startswith('application/json'):
            content = json.loads(content)
        return status, content, response_headers

    def login(self, user_id):
        body = json.dumps({'user_id': user_id}).encode()
        headers = {
            'Host': '127.0.0.1:8000',
            'Connection': 'close',
            'Content-Type': 'application/json',
            'Content-Length': str(len(body)),
        }
        raw = (
            'POST /api/demo/session HTTP/1.1\r\n'
            + ''.join(f'{k}: {v}\r\n' for k, v in headers.items())
            + '\r\n'
        ).encode() + body
        connection = MemoryConnection(raw)
        Handler(connection, ('127.0.0.1', 12345), self.server)
        head, content = connection.output.getvalue().split(b'\r\n\r\n', 1)
        lines = head.decode().split('\r\n')
        self.assertEqual(int(lines[0].split()[1]), 200)
        response_headers = dict(line.split(': ', 1) for line in lines[1:])
        result = json.loads(content)
        self.cookie = response_headers['Set-Cookie'].split(';')[0]
        self.csrf = result['csrf_token']

    def multipart(self, filename, data):
        message = EmailMessage()
        message.set_type('multipart/form-data')
        message.set_param('boundary', 'test-boundary')
        part = EmailMessage()
        part.set_content(data, maintype='application', subtype='octet-stream')
        part['Content-Disposition'] = f'form-data; name="file"; filename="{filename}"'
        message.attach(part)
        raw = message.as_bytes()
        boundary = b'test-boundary'
        # Build a predictable valid multipart request.
        body = (
            b'--' + boundary + b'\r\n'
            + f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
            + b'Content-Type: application/octet-stream\r\n\r\n'
            + data + b'\r\n--' + boundary + b'--\r\n'
        )
        return body, 'multipart/form-data; boundary=test-boundary'

    def test_supported_pdf_upload_and_listing(self):
        self.login(1)
        body, content_type = self.multipart('notes.pdf', b'%PDF-1.4 test')
        status, result, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type
        )
        self.assertEqual(status, 201, result)
        self.assertEqual(result['material']['filename'], 'notes.pdf')
        status, listing, _ = self.request('GET', '/api/groups/1/materials')
        self.assertEqual(status, 200)
        self.assertEqual(listing['materials'][0]['filename'], 'notes.pdf')

    def test_unsupported_extension_is_rejected(self):
        self.login(1)
        body, content_type = self.multipart('virus.exe', b'not allowed')
        status, result, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type
        )
        self.assertEqual(status, 415)
        self.assertIn('Unsupported file format', result['error'])
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM materials').fetchone()[0], 0)

    def test_oversized_file_is_rejected_without_record(self):
        self.login(1)
        body, content_type = self.multipart('large.txt', b'a' * (MAX_UPLOAD_BYTES + 1))
        status, result, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type
        )
        self.assertEqual(status, 413)
        self.assertIn('too large', result['error'].lower())
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM materials').fetchone()[0], 0)

    def test_student_cannot_upload_and_nonmember_cannot_list(self):
        self.login(2)
        body, content_type = self.multipart('notes.txt', b'hello')
        status, _, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type
        )
        self.assertEqual(status, 403)
        self.login(4)
        status, _, _ = self.request('GET', '/api/groups/1/materials')
        self.assertEqual(status, 403)

    def test_bad_pdf_content_is_rejected(self):
        self.login(1)
        body, content_type = self.multipart('notes.pdf', b'not a PDF')
        status, result, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type
        )
        self.assertEqual(status, 415)
        self.assertIn('does not match PDF', result['error'])


    def test_database_failure_removes_uploaded_file_and_record(self):
        self.login(1)

        with connect(self.database) as db:
            db.execute("""
                CREATE TRIGGER reject_material_insert
                BEFORE INSERT ON materials
                BEGIN
                    SELECT RAISE(ABORT, 'simulated database failure');
                END
            """)

        body, content_type = self.multipart(
            'recovery-test.pdf', b'%PDF-1.4 recovery test'
        )

        status, result, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type
        )

        self.assertEqual(status, 500, result)

        with connect(self.database) as db:
            count = db.execute(
                'SELECT COUNT(*) FROM materials'
            ).fetchone()[0]

        self.assertEqual(count, 0)
        self.assertEqual(list(self.upload_dir.iterdir()), [])


    def test_retry_after_database_failure_creates_only_one_record_and_file(self):
        self.login(1)

        with connect(self.database) as db:
            db.execute("""
                CREATE TRIGGER reject_material_insert
                BEFORE INSERT ON materials
                BEGIN
                    SELECT RAISE(ABORT, 'simulated database failure');
                END
            """)

        body, content_type = self.multipart(
            'retry-test.pdf', b'%PDF-1.4 retry test'
        )

        status, _, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type
        )
        self.assertEqual(status, 500)

        with connect(self.database) as db:
            db.execute('DROP TRIGGER reject_material_insert')

        status, result, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type
        )
        self.assertEqual(status, 201, result)

        with connect(self.database) as db:
            count = db.execute(
                'SELECT COUNT(*) FROM materials'
            ).fetchone()[0]

        self.assertEqual(count, 1)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 1)


    def test_same_idempotency_key_returns_original_upload(self):
        self.login(1)
        body, content_type = self.multipart(
            'same-upload.pdf', b'%PDF-1.4 same upload'
        )
        headers = {'Idempotency-Key': 'upload-retry-001'}

        first_status, first_result, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type, headers
        )
        second_status, second_result, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type, headers
        )

        self.assertEqual(first_status, 201, first_result)
        self.assertEqual(second_status, 200, second_result)
        self.assertEqual(
            first_result['material']['id'],
            second_result['material']['id']
        )
        with connect(self.database) as db:
            count = db.execute('SELECT COUNT(*) FROM materials').fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 1)

    def test_same_idempotency_key_with_different_upload_is_rejected(self):
        self.login(1)
        headers = {'Idempotency-Key': 'upload-retry-002'}

        body1, content_type = self.multipart(
            'first.pdf', b'%PDF-1.4 first file'
        )
        body2, _ = self.multipart(
            'second.pdf', b'%PDF-1.4 second file'
        )

        status1, result1, _ = self.request(
            'POST', '/api/groups/1/materials', body1, content_type, headers
        )
        status2, result2, _ = self.request(
            'POST', '/api/groups/1/materials', body2, content_type, headers
        )

        self.assertEqual(status1, 201, result1)
        self.assertEqual(status2, 409, result2)
        with connect(self.database) as db:
            count = db.execute('SELECT COUNT(*) FROM materials').fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 1)

    def test_different_idempotency_keys_create_separate_uploads(self):
        self.login(1)
        body, content_type = self.multipart(
            'separate.pdf', b'%PDF-1.4 separate upload'
        )

        first_status, first_result, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type,
            {'Idempotency-Key': 'upload-separate-001'}
        )
        second_status, second_result, _ = self.request(
            'POST', '/api/groups/1/materials', body, content_type,
            {'Idempotency-Key': 'upload-separate-002'}
        )

        self.assertEqual(first_status, 201, first_result)
        self.assertEqual(second_status, 201, second_result)
        self.assertNotEqual(
            first_result['material']['id'],
            second_result['material']['id']
        )
        with connect(self.database) as db:
            count = db.execute('SELECT COUNT(*) FROM materials').fetchone()[0]
        self.assertEqual(count, 2)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 2)


class MaterialSchemaCompatibilityTests(unittest.TestCase):
    def test_legacy_upload_rows_survive_schema_migration_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.db'
            initialize(path)
            with connect(path) as db:
                seed(db)
                db.execute('DROP TABLE materials')
                db.execute('''CREATE TABLE materials (
                    id INTEGER PRIMARY KEY,group_id INTEGER NOT NULL REFERENCES study_groups(id),
                    uploaded_by INTEGER NOT NULL REFERENCES users(id),filename TEXT NOT NULL,
                    stored_name TEXT NOT NULL UNIQUE,content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL CHECK(size_bytes>0),created_at INTEGER NOT NULL)''')
                db.execute("INSERT INTO materials VALUES(42,1,1,'notes.txt','abc.txt','text/plain',5,1700000000)")
            initialize(path);initialize(path)
            with connect(path) as db:
                row=db.execute('SELECT * FROM materials WHERE id=42').fetchone()
                self.assertEqual((row['title'],row['original_name'],row['stored_name'],row['size_bytes']),('notes.txt','notes.txt','abc.txt',5))
                self.assertEqual(row['created_at'],'2023-11-14 22:13:20')
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_new_upload_can_be_downloaded_with_shared_viewer(self):
        fixture=UploadTests(methodName='test_supported_pdf_upload_and_listing')
        fixture.setUp()
        try:
            fixture.login(1)
            data=b'%PDF-1.4 shared download'
            body,mime=fixture.multipart('new-notes.pdf',data)
            status,result,_=fixture.request('POST','/api/groups/1/materials',body,mime)
            self.assertEqual(status,201)
            mid=result['material']['id']
            status,saved,headers=fixture.request('GET',f'/api/materials/{mid}/download')
            self.assertEqual((status,saved),(200,data))
            self.assertIn('new-notes.pdf',headers['Content-Disposition'])
            self.assertEqual(fixture.request('GET',f'/api/materials/{mid}/view')[0],200)
        finally:
            fixture.tearDown()


    def test_unmigratable_legacy_row_is_not_deleted(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.db'
            initialize(path)
            with connect(path) as db:
                seed(db)
                db.execute('DROP TABLE materials')
                db.execute("""CREATE TABLE materials (
                    id INTEGER PRIMARY KEY,group_id INTEGER,uploaded_by INTEGER,
                    filename TEXT,stored_name TEXT,content_type TEXT,
                    size_bytes INTEGER,created_at INTEGER)""")
                db.execute('INSERT INTO materials VALUES(1,1,1,?,?,?,?,?)',('x'*256,'legacy.txt','text/plain',1,1700000000))
            with self.assertRaises(sqlite3.IntegrityError):
                initialize(path)
            with connect(path) as db:
                self.assertEqual(db.execute('SELECT filename FROM materials').fetchone()[0],'x'*256)
                self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='materials_migrated'").fetchone())


if __name__ == '__main__':
    unittest.main()
