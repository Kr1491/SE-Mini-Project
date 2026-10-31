# StudySpace — role dashboards, group folders and materials

StudySpace opens a role-specific dashboard with database-backed summaries, scoped groups, and navigation for students, instructors, and administrators. #6 incorporates merged role access (#5), folders (#7), and material viewing/downloading (#12), linking the protected workspaces without replacing their authorization checks. The basic login page uses the merged registration password helpers. Administrator user/role/access management is now available; registration UI and quiz features remain separate integration work.

## Run locally

Use Python 3.11+ on macOS or Linux. No Python packages or frontend build step are required.

```bash
mkdir -p var
chmod 700 var
python3 server.py --demo --port 8003
```

Open **http://127.0.0.1:8003/login** for sign-in or a sample account. The material library is at `/materials`. Open `/` or `/dashboard` for the role-specific dashboard. Its folder action opens `/access#folders-panel`; its material action opens `/materials`. The access-verification console and folder form remain at `/access`. Stop with **Ctrl+C**.

Explicit `--demo` creates five small sample resources: PDF, PNG, Python source, DOCX, and private-group text. Student and instructor accounts see four; the administrator sees all five; the student without memberships sees none. This is a local fixture selector, not credential login or uploading. Demo accounts/groups must be unchanged fixtures in a dedicated database; fixture conflicts fail without overwriting existing data. Existing #5 demo databases with the correct marker can gain the material fixtures. Files with conflicting names or bytes are never overwritten.

By default, demo mode uses `var/demo-access.db` and private `var/demo-materials/`; normal mode uses `var/issue5.db` and `var/materials/`. Override with `--database` and `--storage`. Do not point demo mode at real data. Database permissions are `0600`, and database/storage directories must be privately owned `0700` directories. Normal mode disables sample selection and rejects demo tokens. Credential login now verifies existing registered accounts; see [login.md](docs/login.md) for normal-mode account setup and HTTPS cookie configuration.

## Sign in

Open `/login` for the email/password form. Registered accounts sign in to their role dashboard and can Sign out from the profile. In local demo mode, use the clearly labelled sample account buttons; fixtures have no passwords. [Setup, API and verification details](docs/login.md).

## Role dashboards

Students see their groups and active study partners; instructors see their owned/joined groups and teaching tools; administrators see global active-user/group/membership counts and administration tools. Summaries come from the current database. Direct `/dashboard/{student|instructor|administrator}` pages and corresponding APIs require the exact authenticated role. Account switching clears old private content and ignores stale responses. Dashboard links preserve the authorization checks of the destination feature; they retain the authorization checks of those features. Quiz tools remain unavailable until implemented. Administrators can open Users and permissions to manage registered accounts.

## Administrator accounts and permissions (#18)

Sign in as a registered Administrator and open **Users and permissions** on the dashboard, or `/admin/users`. Search/filter accounts, review role capabilities and confirm changes to another user's role or active/suspended status. Every access change revokes that user's existing sessions, records an audit entry and persists to the database. Self-demotion/suspension and stale edits are blocked. Students and instructors cannot open the page or use the management API.

Explicit `--demo` accounts are read-only so their fixed identities remain valid. Use the separate local test accounts in normal mode to try edits. [Preview/commit commands](docs/issue-18-workflow.md), [test evidence](docs/issue-18-test-results.md) and [PR description](docs/issue-18-pr.md).

## Group folders

Open `/access` to use the group folder picker and creation form alongside the access-verification console. Instructors can create folders in groups they own, administrators in any group, and members can read their permitted groups' folders. Names are trimmed/Unicode-normalized, limited to 1–80 characters, and unique without case differences within a group. Records persist across restarts; validation, duplicate feedback, CSRF protection, and group access checks remain active.

## Library behavior

- Filter by an authorized study group, refresh, and page through up to 24 resources at a time.
- Preview UTF-8 text/code as literal text, PDFs, and supported PNG/JPEG/GIF/WebP images. Large text above 2 MiB uses download instead. PDF display depends on the browser's PDF support; Download remains available.
- Download original file bytes with a safe original filename. Office documents and unsupported/active formats are download-only. The server derives safe inline types from the extension and byte signature rather than trusting stored MIME metadata.
- Downloads stream in bounded 64 KiB chunks. Protected single-byte range requests support PDF seeking and partial transfers; unsupported multipart ranges fall back to a full response.
- Missing, incomplete, unauthorized, or expired-session requests produce clear feedback. Account/group changes clear previews and ignore stale responses.

Material access is **group-scoped**. The #7 folder table and routes are preserved alongside the #12 material schema. Materials currently reference groups; linking uploads to destination folders remains part of the upload integration. Folder association, uploads (#8), and format/size validation before upload (#11) require the documented handoff to Anushree. The generated demo files let this PR be exercised without claiming those modules are complete. The dashboard Materials action now opens `/materials` for students, instructors, and administrators; access remains group-scoped at the API. Unimplemented quiz tools remain Coming soon; the Administrator user-management action is active.

## Checks

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q server.py study_platform tests
node --check static/admin-users.js
node --check static/login.js
node --check static/app.js
node --check static/dashboard.js
node --check static/folders.js
node --check static/materials.js
node --test tests/*.cjs
```

Node.js is required only for frontend tests and syntax checks. The Python suite dispatches actual HTTP handlers over in-memory connections with temporary SQLite databases; it needs no listening port. Frontend tests execute the actual JavaScript with a simulated DOM and fetch responses.

Local results: **143 Python tests** pass on Python 3.12 and 3.14; **65 JavaScript tests** pass. CI retains pinned actions and Python 3.11/3.12 coverage. Live HTTP integration checks pass on a loopback server. Isolated Chrome sign-in/sign-out and administrator-management flows pass; updated remote CI follows the push.

## Issue documents

- [Dashboard PR description — closes #6 only](docs/issue-6-pr.md)
- [Dashboard checks and conflict resolution](docs/issue-6-test-results.md)
- [Finish updating existing PR #25](docs/issue-6-workflow.md)

- [Manual checks and test evidence](docs/issue-12-test-results.md)
- [Step-by-step branch, commit, PR, and board guide](docs/issue-12-workflow.md)
- [PR description — closes #12 only](docs/issue-12-pr.md)
- [Shared authentication, authorization, and upload integration contract](docs/integration.md)
- [Merged #7 folder behavior and checks](docs/issue-7-test-results.md)
- [Earlier #5 review fixes](docs/pr23-review-fixes.md)
