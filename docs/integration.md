# StudySpace — integration contract (#5, #6, #7 and #12)

## Scope

Python 3.11+, SQLite, and HTML/CSS/JavaScript; no package installation. Merged #5 supplies reusable sessions, server-side role/group authorization, and an access-verification page. #12 adds the group-scoped material catalog, preview, and downloading. Merged #7 supplies authorized group folders. #6 adds the role-specific landing dashboards while retaining both features. Teammates' authentication, group, membership, and upload modules remain separate work.

## Shared schema

`study_platform/db.py` defines `users`, `study_groups`, `memberships`, and `sessions`. Group records/memberships are minimal prerequisite fixtures for testing scope, not group creation/joining endpoints. #12 adds the `materials` schema below. The merged #7 `folders` schema and operations are preserved. Materials currently reference groups independently; folder association is part of the upload integration contract below.

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
- Krishna's #7 folders and #12 materials are merged. #6 dashboards incorporate the latest main and link both protected workspaces. Recheck the combined journey after each merge.
- Every protected feature must call the relevant role/group authorization helpers on the server; hiding buttons alone does not protect an API.
- Agree schema changes and test the real authenticated journey after merging the modules.


## Materials handoff to Anushree (#8/#11)

The `materials` table in `db.py` contains `id`, `group_id`, `title`, `original_name`, unique `stored_name`, `content_type`, `size_bytes`, `uploaded_by`, and `created_at`. Group/user foreign keys and required lengths/nonnegative integer size are enforced. IDs are generated by SQLite; never assume fixture IDs for uploaded records. This first independent schema has no folder foreign key. Agree the `folder_id` migration with the upload module now that #7 is merged and check that a folder belongs to the material's group before accepting it.

Upload implementation must authenticate, check permission to publish to the group, and enforce its file format/size rules **before** making a resource visible. Generate an opaque flat storage key such as a UUID plus extension, matching `[A-Za-z0-9][A-Za-z0-9._-]{0,179}`. Never use a user's original filename as a path or permit directories/symlinks. Initialize storage with `initialize_storage`; save private regular files with mode `0600` under the privately owned `0700` directory. The server requires macOS/Linux POSIX safe-open support.

Use an exclusive temporary file in that directory, write and close the entire content, then publish under a unique immutable final key without replacing existing files. Insert metadata in a database transaction only after the final file exists; remove the new file if metadata insertion fails. A size mismatch returns 404 and never streams partial uploads. Once published, do not rewrite a key in place; replace a resource through a new key plus metadata update and clean up the previous file afterward. Store the exact original byte length; `content_type` is metadata and is not trusted as an inline response type.

Example metadata insertion **after** authorized validation and successful file finalization:

```python
with connect(database_path) as db:
    db.execute("""INSERT INTO materials
        (group_id,title,original_name,stored_name,content_type,size_bytes,uploaded_by)
        VALUES(?,?,?,?,?,?,?)""",
        (group_id, title, original_name, generated_key, detected_type,
         final_byte_length, verified_user_id))
```

This snippet is a schema contract, not an upload endpoint. The demo fixture helper must never be called to populate real authentication databases.

| Endpoint | Behavior |
|---|---|
| `GET /materials` | Library shell. Protected data loads through the authenticated API. |
| `GET /api/materials?group_id=1&limit=24&offset=0` | Authorized groups/material metadata; group optional, limit 1–100, offset nonnegative. No storage keys or private paths are returned. |
| `GET /api/materials/{id}/view` | Safe inline text, PDF, or supported raster image; other content is attachment-only. |
| `GET /api/materials/{id}/download` | Original bytes with attachment disposition and sanitized UTF-8 filename. |
| `HEAD /api/materials/{id}/view` or `/download` | Same authorization and file headers without a response body. |

All material endpoints require `materials.read`; administrators may read all groups, instructors/other users only groups they own or belong to. Membership, role, session expiry, and active-state changes affect the next request. Both direct URLs and byte-range requests repeat these checks. Files remain outside the static asset directory. Unsafe storage keys, symlinks, special files, missing/incomplete files, and insecure storage roots are rejected. Text/code is always `text/plain`, and HTML/SVG/Office/binary content stays attachment-only. Responses use `nosniff`, restrictive CSP, same-origin resource policy, and private/no-store caching.

Single byte ranges return 206/Content-Range; valid unsatisfiable ranges return 416. Unsupported/malformed/multipart ranges are ignored in favor of a full response. HEAD ignores Range. Since no range validators are issued, If-Range requests receive a full response. These choices follow [HTTP range semantics](https://www.rfc-editor.org/rfc/rfc9110.html#name-range). Download names use a stripped leaf name and UTF-8 `filename*` per [Content-Disposition](https://www.rfc-editor.org/rfc/rfc6266.html#section-4.3). Safe file opening uses [Python POSIX dir_fd support](https://docs.python.org/3.11/library/os.html#os.open).

## Issue #7 — folder contract

- `GET /api/groups`: authorized group metadata for the picker; no group creation/membership mutation.
- `GET /api/groups/{id}/folders`: returns `group`, `folders`, and server-derived `can_create`.
- `POST /api/groups/{id}/folders`: accepts JSON `{"name":"Unit 1 notes"}` and the session CSRF header; returns 201 with `folder`. The transaction commits before sending success.
- `GET /folders.js`: frontend module loaded before app.js. The access application calls its optional `StudyFolders.load(session)` after login/session detection and resets it before account switching.

The additive `folders` table stores ID, group ID, display name, normalized casefold name key, creator ID, and creation timestamp. It enforces group-scoped unique keys and group/user foreign keys. The existing #5 schema and demo-fixture identity rules remain intact; added folder records do not alter reserved user/group/membership fixtures.

Names use Unicode NFC, trimmed boundaries, 1–80 characters, and no control/hidden formatting characters. A group-scoped duplicate returns 409. The write transaction covers authorization and insertion, so concurrent duplicates produce one record. SQL/HTML-like names remain data and are rendered with textContent.

Students/member instructors can read authorized groups' folders. Folder creation requires administrator access or instructor ownership of that group, consistent with the #5 policy. An instructor's membership alone does not grant management authority.

Anushree's later upload implementation should reference a valid folder in the same group and use generated storage keys rather than display folder names as filesystem paths. The folder feature does not implement uploads; #12 adds the separate material schema above. Jiya's real group creation should continue setting study_groups.created_by; the group picker recognizes that owner and authorized memberships.

## Issue #6 — dashboard contract

The root `/` and `/dashboard` serve the new dashboard shell. The existing access/folder workspace is preserved at `/access`; its app.js, style.css and folders.js retain their behavior.

- `GET /api/dashboard` returns the current user's role-specific profile, navigation, summaries, scoped groups, available/pending actions and update timestamp.
- `GET /api/dashboard/{student|instructor|administrator}` and matching `/dashboard/{role}` pages require the authenticated role to match; administrators do not impersonate other role dashboards through those URLs.
- Query-string roles/user IDs are ignored. User identity, role, active status and demo provenance come from the existing session checks.
- Student partner counts include active creators/members only within accessible groups. Instructor counts distinguish owned groups from memberships. Workspace-wide counts are returned only to administrators.
- No password hashes, session tokens or CSRF values are included in dashboard JSON. Profile data belongs to the current account.
- Navigation/action destinations are defined by the server and restricted by the frontend's allowlist. Unimplemented tools are unavailable, without fake counters or active links.

The dashboard reads existing users/groups/memberships without a schema migration. `build_dashboard(..., features={'folders': ..., 'materials': ...})` receives server-derived capability information; the folder action is available only when the server has the #7 creation implementation loaded. It opens `/access#folders-panel`, where the existing group picker and authorization apply. The Materials action is available to each supported role when its material-serving capability is present and the role has `materials.read`; it opens `/materials`. The frontend allowlist permits that exact path. Both destinations retain their own session, role and group checks; dashboard visibility does not grant resource access.

Jiya's future authentication UI should navigate to `/dashboard` after verified login/session creation. New group/membership records are reflected on refresh. Other feature owners should enable their tool metadata only after their protected routes exist. Preserve server-side role/group checks in every feature; dashboard visibility alone is not authorization.
