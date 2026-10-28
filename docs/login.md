# Basic sign-in

`/login` provides email/password sign-in using the PBKDF2 password format already supplied by the registration module. Successful sign-in opens `/dashboard`; the profile's Sign out button revokes the current session and returns to `/login`.

## Local demo

```bash
mkdir -p var
chmod 700 var
python3 server.py --demo --port 8003
```

Open `http://127.0.0.1:8003/login`. Choose a clearly labelled Student, Instructor, Administrator or Student without groups sample account. These existing fixtures have no passwords. Email/password submission in demo mode explains that the sample selector must be used. Demo sessions remain tagged and are rejected in normal mode.

## Existing real accounts

```bash
python3 server.py --port 8004
```

Open `http://127.0.0.1:8004/login` and use an account registered in `var/issue5.db` with `study_platform.auth.register_user`, or supply the same `--database` path used by the registration integration. The normal-mode sample selector and endpoint are disabled. Instructor/Administrator accounts must already have been provisioned through trusted account-management setup; submitted roles do not grant privileges.

For an empty local development database, this example uses the existing registration helper to create one Student and prompts for a password without placing it in shell history. It refuses an existing duplicate email rather than overwriting it:

```bash
python3 - <<'PY'
from getpass import getpass
from study_platform.auth import register_user
from study_platform.db import initialize, connect

path = 'var/issue5.db'
initialize(path)
with connect(path) as db:
    account = register_user(db, {
        'name': 'Local Student',
        'email': 'student@example.test',
        'password': getpass('Choose a password (12–128 characters): '),
    })
print('Created:', account['email'])
PY
```

The registration form, password reset and account-management UI remain separate integration work. This change adds no default real-account password.

## API behavior

- `POST /api/login` accepts JSON `email` and `password`, verifies an active registered account, rotates any previous browser session and commits before sending its cookie. Email is trimmed/case-normalized; passwords are preserved exactly. Unknown accounts, bad passwords, passwordless accounts and inactive accounts receive the same generic error. Cross-origin login requests are denied.
- `POST /api/logout` requires the active session and its `X-CSRF-Token`. It deletes the token hash, commits, and expires the cookie. Old tokens cannot be reused.
- Session cookies use HttpOnly, SameSite=Strict and an eight-hour lifetime. Use `--secure-cookies` when serving through an HTTPS reverse proxy so both issue/expiry cookies include Secure. Do not use that flag on a plain HTTP preview.
- A signed-in visitor to `/login` goes to the dashboard. Duplicate submissions and conflicting sample/login actions are blocked during a pending request. Errors remain visible and recoverable.

This is a basic local sign-in flow; deployment-specific abuse throttling and account recovery are not added.

## Material compatibility repair

Latest main had two incompatible `materials` table definitions: the newly merged upload schema used `filename`, while the existing viewer and demo fixtures expected `title`/`original_name`. Fresh demo startup and existing material tests failed. This change restores one shared schema, migrates legacy metadata transactionally while preserving IDs and names, and uses the protected viewer for downloads. Invalid legacy rows roll back rather than being deleted.

New uploads use the same private storage directory and metadata as the viewer. The group upload/listing API keeps its existing `filename` response field. If an earlier installation stored files in `var/uploads`, retain that directory and run with `--storage var/uploads`; schema migration does not move existing file bytes. Existing #12 storage continues to work normally.

## Verification

119 Python tests pass on Python 3.12 and 3.14; 52 JavaScript tests pass. Python compilation, login/dashboard JavaScript syntax, and `git diff --check` pass. A real isolated Chrome session verified invalid-password recovery, email/password sign-in, Student dashboard rendering, cross-role denial, logout, and return to the guest login page. The demo login layout was checked at desktop width. CI adds syntax checking for login.js; the remote result follows the push.
