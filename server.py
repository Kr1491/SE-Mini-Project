#!/usr/bin/env python3
"""Run issue #5 access verification: python3 server.py --demo (local fixtures only)."""
import argparse
import hashlib
import json
import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from study_platform.db import connect, initialize
from study_platform.demo import seed
from study_platform.security import APIError, COOKIE_NAME, PERMISSIONS, create_session, current_session, group_access, require_permission

ROOT = Path(__file__).resolve().parent


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
                # Replace the previous sample session when switching accounts.
                try:
                    from http.cookies import SimpleCookie
                    cookie=SimpleCookie(self.headers.get('Cookie',''))
                    if COOKIE_NAME in cookie:
                        db.execute('DELETE FROM sessions WHERE token_hash=?',
                                   (hashlib.sha256(cookie[COOKIE_NAME].value.encode()).hexdigest(),))
                except Exception:
                    pass
                token,csrf=create_session(db,uid)
                return self.json(200,{'csrf_token':csrf}, {'Set-Cookie':f'{COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})
            user=current_session(db,self.headers.get('Cookie'))
            if method=='POST':
                if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),user['csrf_token']):
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
                group = group_access(db, user, int(match[1]), manage=bool(match[2]))
                return self.json(200, {'allowed': True, 'message': f'Access verified for {group["name"]}.', 'group': group})
            if method == 'POST' and path == '/api/access/check':
                data = self.body()
                permission = data.get('permission')
                if not isinstance(permission, str):
                    raise APIError(400, 'Provide a permission name.')
                require_permission(user, permission)
                return self.json(200, {'allowed': True, 'permission': permission})
            raise APIError(404,'Route not found.')


def make_server(database,port=8000,demo=False,host='127.0.0.1'):
    if demo and host not in ('127.0.0.1','localhost','::1'):
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
    parser.add_argument('--database',default=str(ROOT/'var/issue5.db'))
    args=parser.parse_args()
    server=make_server(args.database,args.port,args.demo)
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
