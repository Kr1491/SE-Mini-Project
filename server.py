#!/usr/bin/env python3
"""Run issue #5 access verification: python3 server.py --demo (local fixtures only)."""
import argparse
import hashlib
import json
import os
import uuid
from email.parser import BytesParser
from email.policy import default as email_policy
import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
from urllib.parse import urlsplit
from study_platform.db import connect, initialize
from study_platform.demo import seed, validate_demo
from study_platform.security import APIError, COOKIE_NAME, PERMISSIONS, create_session, current_session, group_access, require_permission

ROOT = Path(__file__).resolve().parent

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    '.pdf': 'application/pdf',
    '.txt': 'text/plain',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}



class Handler(BaseHTTPRequestHandler):
    server_version = 'StudyPlatform/1.0'

    def do_GET(self):
        self.handle_request('GET')

    def do_POST(self):
        self.handle_request('POST')

    def send_bytes(self, status, content, content_type='application/json; charset=utf-8', extra=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for key,value in (extra or {}).items():
            self.send_header(key,value)
        self.end_headers()
        self.wfile.write(content)

    def json(self, status, data, extra=None):
        self.send_bytes(status,json.dumps(data).encode(),extra=extra)

    def body(self):
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            raise APIError(415, 'Send JSON data using application/json.')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise APIError(400, 'Invalid request length.')
        if length < 0 or length > 16384:
            raise APIError(413, 'Request is too large.')
        try:
            data = json.loads(self.rfile.read(length))
        except (ValueError,UnicodeError):
            raise APIError(400, 'Invalid JSON request.')
        if not isinstance(data,dict):
            raise APIError(400, 'Expected a JSON object.')
        return data

    def handle_request(self, method):
        try:
            self.dispatch(method)
        except APIError as exc:
            self.json(exc.status, {'error':exc.message})
        except (BrokenPipeError,ConnectionResetError):
            pass
        except Exception as exc:
            print(f'Request failed: {type(exc).__name__}: {exc}', file=sys.stderr)
            self.json(500, {'error':'The request could not be completed. Please try again.'})

    def dispatch(self, method):
        path = urlsplit(self.path).path
        if method=='GET' and path in ('/','/app.js','/style.css'):
            filename={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
            mime={'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/style.css':'text/css; charset=utf-8'}[path]
            return self.send_bytes(200,(ROOT/'static'/filename).read_bytes(),mime)
        if method=='GET' and path=='/api/health':
            return self.json(200,{'ok':True,'demo':self.server.demo})
        with connect(self.server.database) as db:
            if path=='/api/demo/session' and method=='POST':
                if not self.server.demo:
                    raise APIError(404,'Route not found.')
                data=self.body()
                uid=data.get('user_id')
                if type(uid)!=int or uid not in (1,2,3,4):
                    raise APIError(400,'Choose a sample account.')
                if not db.in_transaction:
                    db.execute('BEGIN IMMEDIATE')
                try:
                    validate_demo(db)
                except ValueError as exc:
                    raise APIError(409, str(exc))
                # Malformed cookies may be ignored; database errors must surface.
                cookie = SimpleCookie()
                try:
                    cookie.load(self.headers.get('Cookie', ''))
                except CookieError:
                    cookie.clear()
                if COOKIE_NAME in cookie:
                    db.execute('DELETE FROM sessions WHERE token_hash=?',
                               (hashlib.sha256(cookie[COOKIE_NAME].value.encode()).hexdigest(),))
                token,csrf=create_session(db,uid,demo=True)
                # Persist the token/revocation before sending it to the browser.
                db.commit()
                return self.json(200,{'csrf_token':csrf}, {'Set-Cookie':f'{COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})
            user=current_session(db,self.headers.get('Cookie'),allow_demo=self.server.demo)
            if method=='POST':
                if not secrets.compare_digest(self.headers.get('X-CSRF-Token','').encode('utf-8'),user['csrf_token'].encode('utf-8')):
                    raise APIError(403,'Invalid request token. Refresh the page and try again.')
            safe_user={k:user[k] for k in ('id','name','email','role')}
            if path=='/api/session' and method=='GET':
                return self.json(200,{'user':safe_user,'csrf_token':user['csrf_token'],'permissions':PERMISSIONS[user['role']]})
            permission_routes = {
                '/api/access/instructor': 'instructor.summary',
                '/api/access/admin': 'admin.summary',
                '/api/access/quiz-create': 'quiz.create',
            }
            if method == 'GET' and path in permission_routes:
                permission = permission_routes[path]
                require_permission(user, permission)
                return self.json(200, {'allowed': True, 'message': f'{permission} permission verified.'})
            match = re.fullmatch(r'/api/access/groups/([1-9][0-9]*)(/manage)?', path)
            if method == 'GET' and match:
                raw_id = match[1]
                if len(raw_id) > 19 or int(raw_id) > 9223372036854775807:
                    raise APIError(400, 'Invalid study group ID.')
                group = group_access(db, user, int(raw_id), manage=bool(match[2]))
                return self.json(200, {'allowed': True, 'message': f'Access verified for {group["name"]}.', 'group': group})
            if method == 'GET' and path == '/api/groups':
                groups = db.execute(
                    '''SELECT g.id, g.name, g.created_by
                       FROM memberships m
                       JOIN study_groups g ON g.id = m.group_id
                       WHERE m.user_id = ?
                       ORDER BY g.name COLLATE NOCASE, g.id''',
                    (user['id'],)
                ).fetchall()
                return self.json(200, {'groups': [dict(g) for g in groups]})

            join_match = re.fullmatch(r'/api/groups/([1-9][0-9]*)/join', path)
            if method == 'POST' and join_match:
                raw_id = join_match[1]
                if len(raw_id) > 19 or int(raw_id) > 9223372036854775807:
                    raise APIError(400, 'Invalid study group ID.')
                if user['role'] != 'student':
                    raise APIError(403, 'Only students can join study groups.')

                group_id = int(raw_id)
                group = db.execute(
                    'SELECT id, name, created_by FROM study_groups WHERE id = ?',
                    (group_id,)
                ).fetchone()
                if not group:
                    raise APIError(404, 'Study group not found.')

                result = db.execute(
                    'INSERT OR IGNORE INTO memberships (group_id, user_id) VALUES (?, ?)',
                    (group_id, user['id'])
                )
                already_member = result.rowcount == 0
                return self.json(
                    200 if already_member else 201,
                    {'joined': True, 'already_member': already_member, 'group': dict(group)}
                )


            upload_match = re.fullmatch(r'/api/groups/([1-9][0-9]*)/materials', path)

            if method == 'POST' and upload_match:
                raw_id = upload_match[1]
                if len(raw_id) > 19 or int(raw_id) > 9223372036854775807:
                    raise APIError(400, 'Invalid study group ID.')

                group = group_access(db, user, int(raw_id), manage=True)

                content_type = self.headers.get('Content-Type', '')
                if not content_type.lower().startswith('multipart/form-data'):
                    raise APIError(400, 'Upload must use multipart/form-data.')

                raw_length = self.headers.get('Content-Length', '')
                if not raw_length.isdigit():
                    raise APIError(400, 'Invalid upload size.')
                length = int(raw_length)
                if length > MAX_UPLOAD_BYTES + 65536:
                    raise APIError(413, 'File too large. Maximum file size is 5 MiB.')
                if length <= 0:
                    raise APIError(400, 'The uploaded file is empty.')

                raw_body = self.rfile.read(length)
                message = BytesParser(policy=email_policy).parsebytes(
                    ('Content-Type: ' + content_type + '\r\n'
                     'MIME-Version: 1.0\r\n\r\n').encode('ascii') + raw_body
                )
                if not message.is_multipart():
                    raise APIError(400, 'Invalid multipart upload.')

                files = [
                    part for part in message.iter_parts()
                    if part.get_param('name', header='content-disposition') == 'file'
                    and part.get_content_disposition() == 'form-data'
                ]
                if len(files) != 1:
                    raise APIError(400, 'Provide exactly one file in the file field.')

                part = files[0]
                filename = part.get_filename()
                if not isinstance(filename, str) or not filename.strip():
                    raise APIError(400, 'The file must have a filename.')

                filename = Path(filename.replace('\\', '/')).name.strip()
                extension = Path(filename).suffix.lower()
                if not filename or filename in ('.', '..') or extension not in ALLOWED_EXTENSIONS:
                    raise APIError(415, 'Unsupported file format. Allowed: PDF, TXT, DOCX, PPTX.')

                data = part.get_payload(decode=True) or b''
                if not data:
                    raise APIError(400, 'The uploaded file is empty.')
                if len(data) > MAX_UPLOAD_BYTES:
                    raise APIError(413, 'File too large. Maximum file size is 5 MiB.')

                expected_type = ALLOWED_EXTENSIONS[extension]
                if extension == '.pdf' and not data.startswith(b'%PDF-'):
                    raise APIError(415, 'The file content does not match PDF format.')
                if extension in ('.docx', '.pptx') and not data.startswith(b'PK'):
                    raise APIError(415, 'The file content does not match the selected format.')
                if extension == '.txt':
                    try:
                        data.decode('utf-8')
                    except UnicodeDecodeError:
                        raise APIError(415, 'The file content is not valid UTF-8 text.')
                    if b'\x00' in data:
                        raise APIError(415, 'The file content is not valid text.')

                stored_name = uuid.uuid4().hex + extension
                upload_dir = Path(getattr(self.server, 'upload_dir', ROOT / 'var' / 'uploads'))
                upload_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                if os.name == 'posix':
                    os.chmod(upload_dir, 0o700)
                stored_path = upload_dir / stored_name

                descriptor = os.open(
                    stored_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600
                )
                try:
                    with os.fdopen(descriptor, 'wb') as output:
                        output.write(data)
                    cursor = db.execute(
                        'INSERT INTO materials '
                        '(group_id, uploaded_by, filename, stored_name, content_type, size_bytes, created_at) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (group['id'], user['id'], filename, stored_name,
                         expected_type, len(data), int(__import__('time').time()))
                    )
                except Exception:
                    stored_path.unlink(missing_ok=True)
                    raise

                return self.json(201, {
                    'material': {
                        'id': cursor.lastrowid,
                        'group_id': group['id'],
                        'filename': filename,
                        'content_type': expected_type,
                        'size_bytes': len(data),
                    }
                })

            if method == 'GET' and re.fullmatch(r'/api/groups/[1-9][0-9]*/materials', path):
                raw_id = path.split('/')[3]
                if len(raw_id) > 19 or int(raw_id) > 9223372036854775807:
                    raise APIError(400, 'Invalid study group ID.')
                group = group_access(db, user, int(raw_id))
                rows = db.execute(
                    'SELECT id, group_id, uploaded_by, filename, content_type, size_bytes, created_at '
                    'FROM materials WHERE group_id = ? ORDER BY created_at DESC, id DESC',
                    (group['id'],)
                ).fetchall()
                return self.json(200, {'materials': [dict(row) for row in rows]})

            download_match = re.fullmatch(r'/api/materials/([1-9][0-9]*)/download', path)
            if method == 'GET' and download_match:
                raw_id = download_match[1]
                if len(raw_id) > 19 or int(raw_id) > 9223372036854775807:
                    raise APIError(400, 'Invalid material ID.')
                material = db.execute(
                    'SELECT * FROM materials WHERE id = ?', (int(raw_id),)
                ).fetchone()
                if not material:
                    raise APIError(404, 'Study material not found.')

                group_access(db, user, material['group_id'])
                upload_dir = Path(getattr(self.server, 'upload_dir', ROOT / 'var' / 'uploads'))
                stored_path = upload_dir / material['stored_name']
                try:
                    content = stored_path.read_bytes()
                except OSError:
                    raise APIError(404, 'Stored file is unavailable.')

                safe_filename = material['filename'].replace('"', '').replace('\r', '').replace('\n', '')
                return self.send_bytes(
                    200, content, material['content_type'],
                    {'Content-Disposition': f'attachment; filename="{safe_filename}"'}
                )

            if method == 'POST' and path == '/api/access/check':
                data = self.body()
                permission = data.get('permission')
                if not isinstance(permission, str):
                    raise APIError(400, 'Provide a permission name.')
                require_permission(user, permission)
                return self.json(200, {'allowed': True, 'permission': permission})
            raise APIError(404,'Route not found.')


def make_server(database,port=8000,demo=False,host='127.0.0.1'):
    if ':' in host:
        raise ValueError('IPv6 hosts are not supported by this server. Use 127.0.0.1.')
    if demo and host not in ('127.0.0.1','localhost'):
        raise ValueError('Demo sessions are only available on a loopback address.')
    initialize(database)
    if demo:
        with connect(database) as db:
            seed(db)
    server=ThreadingHTTPServer((host,port),Handler)
    server.database,server.demo=str(database),demo
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo',action='store_true',help='Seed local fixtures and enable sample account selection. Never use with real data.')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--database',help='Use a dedicated private database path; demo defaults to var/demo-access.db.')
    args=parser.parse_args()
    database = args.database or str(ROOT/'var'/('demo-access.db' if args.demo else 'issue5.db'))
    server=make_server(database,args.port,args.demo)
    print(f'Study Platform: http://127.0.0.1:{server.server_port}',flush=True)
    print('Mode: '+('LOCAL DEMO — sample account access enabled.' if args.demo else 'Integration — authentication module must provide sessions.'),flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    main()
