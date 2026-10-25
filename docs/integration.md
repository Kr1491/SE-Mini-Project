# Issue #5 — integration contract

## Scope

Python 3.11+, SQLite, and HTML/CSS/JavaScript; no package installation. This change supplies reusable sessions, server-side role/group authorization, and a generic permission-verification page. It does not implement the three later Krishna issues (#6 dashboards, #7 folders, #12 material access) or the teammates' modules.

## Shared schema

`study_platform/db.py` defines `users`, `study_groups`, `memberships`, and `sessions`. Group records/memberships are minimal prerequisite fixtures for testing scope, not group creation/joining endpoints. Folder/material schemas and operations belong to subsequent changes.

Use `with connect(database_path) as db:` for a foreign-key-enabled connection and automatic commit/rollback/cleanup. Use parameterized SQL. Roles are exactly `student`, `instructor`, and `administrator`.

Normal mode defaults to `var/issue5.db`; demo mode defaults to `var/demo-access.db`, both ignored by Git. On POSIX systems, use a private owner-only database directory (`0700`); initialization creates/tightens the database file to `0600`. A new demo database must be empty, and its fixture marker and reserved records are revalidated at startup and before selecting an account. Conflicting real records cause a refusal rather than fixture reuse. Real authentication can use the same schema with a separate database path, for example `python3 server.py --database var/integration.db`. Demo records have no password hash and are not valid credential-authenticated accounts.

## Authentication handoff to Jiya (#3/#4)

Registration validates required data, rejects duplicate email addresses, and stores a secure password hash. Real login must verify that hash before calling:

```python
from study_platform.db import connect
from study_platform.security import create_session

with connect(database_path) as db:
    token, csrf_token = create_session(db, verified_user_id)
```

After verification, set `study_session=<token>; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800`. Add `Secure` with HTTPS. The database stores only the SHA-256 hash of the random session token. Return the CSRF token to the client. Logout must delete the stored token hash and expire the cookie. Regenerate the session on login. Demo-issued sessions are marked `is_demo=1` and are rejected outside demo mode. The session token is committed before the demo endpoint sends its cookie.

Session-table migration enforces `token_hash TEXT PRIMARY KEY NOT NULL`. Legacy sessions with no mode provenance are invalidated and require a fresh login; already-classified non-null sessions are preserved when tightening the primary key. Never treat a legacy demo token as credential-verified.

Add anonymous registration/login routes before the request dispatcher's `current_session` call. Protected routes derive the user's identity, role, and active state from the database. The demo endpoint must not replace credential verification.

## Authorization policy

| Role | Capabilities |
|---|---|
| Student | Dashboard/read permissions, material reading within authorized groups, quiz attempts. |
| Instructor | Read permissions plus quiz-authoring/instructor permissions; manage folders only in groups they own. |
| Administrator | Read/authoring/admin permissions; access and folder-management authority across groups. |

`require_permission(user, permission)` rejects unauthorized roles. `group_access(db, user, group_id, manage=False)` additionally checks group ownership/membership; `manage=True` requires the folder-management permission and group ownership, except for administrators.

Protected requests reject missing, forged, expired, and inactive-user sessions. Database role changes and membership revocation affect the next request. Client-supplied roles/user IDs do not grant authority.

The mapping establishes permissions for later features; it does not implement those features. The team should document any later decision to allow delegated management by students or non-owner instructors.

## Existing endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Public readiness and explicit demo-mode status. |
| `GET /api/session` | Current user, CSRF token, and permission list. |
| `GET /api/access/instructor` | Guarded instructor permission probe. |
| `GET /api/access/admin` | Guarded administrator permission probe. |
| `GET /api/access/quiz-create` | Guarded quiz-authoring permission probe. |
| `GET /api/access/groups/{id}` | Group-scoped read authorization probe. |
| `GET /api/access/groups/{id}/manage` | Group-scoped management authorization probe. |
| `POST /api/access/check` | JSON `{"permission":"quiz.create"}`; requires the session's `X-CSRF-Token` and permission. |
| `POST /api/demo/session` | Sample account selection, available only with explicit `--demo` and loopback binding. |

Errors return `{"error":"message"}`. Common statuses: 400 invalid request, 401 missing/invalid session, 403 unauthorized/invalid CSRF, 404 missing route/group, 413 excessive JSON body, and 415 unsupported content type.

## Teammate and follow-up integration

- Jiya adds registration/login/logout and group creation in her PRs.
- Anushree adds membership management, uploads, and upload validation in her PRs.
- Krishna's next PRs separately add #6, then #7, then #12.
- Every protected feature must call the relevant role/group authorization helpers on the server; hiding buttons alone does not protect an API.
- Agree schema changes and test the real authenticated journey after merging the modules.
