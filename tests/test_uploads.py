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

    def request(self, method, path, body=b'', content_type=None):
        headers = {
            'Host': '127.0.0.1:8000',
            'Connection': 'close',
            'Cookie': self.cookie,
            'X-CSRF-Token': self.csrf,
            'Content-Length': str(len(body)),
        }
        if content_type:
            headers['Content-Type'] = content_type
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


if __name__ == '__main__':
    unittest.main()
