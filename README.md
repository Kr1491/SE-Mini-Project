# StudySpace — group folders and material access

The material library lists resources from groups the current user can access, previews supported files, and downloads their original bytes. Every catalog, preview, download, and HEAD request verifies the server session, role permission, and group access. This branch combines material access (#12) with merged role access (#5) and group folders (#7). Dashboard #6 remains in its separate review PR.

## Run locally

Use Python 3.11+ on macOS or Linux. No Python packages or frontend build step are required.

```bash
mkdir -p var
chmod 700 var
python3 server.py --demo --port 8003
```

Open **http://127.0.0.1:8003/materials**. The existing access-verification console remains at `/` and links to the library. Stop with **Ctrl+C**.

Explicit `--demo` creates five small sample resources: PDF, PNG, Python source, DOCX, and private-group text. Student and instructor accounts see four; the administrator sees all five; the student without memberships sees none. This is a local fixture selector, not credential login or uploading. Demo accounts/groups must be unchanged fixtures in a dedicated database; fixture conflicts fail without overwriting existing data. Existing #5 demo databases with the correct marker can gain the material fixtures. Files with conflicting names or bytes are never overwritten.

By default, demo mode uses `var/demo-access.db` and private `var/demo-materials/`; normal mode uses `var/issue5.db` and `var/materials/`. Override with `--database` and `--storage`. Do not point demo mode at real data. Database permissions are `0600`, and database/storage directories must be privately owned `0700` directories. Normal mode disables sample selection and rejects demo tokens; Jiya's credential login integration must issue real sessions as described in [integration.md](docs/integration.md).

## Group folders

Open `/` to use the group folder picker and creation form alongside the access-verification console. Instructors can create folders in groups they own, administrators in any group, and members can read their permitted groups' folders. Names are trimmed/Unicode-normalized, limited to 1–80 characters, and unique without case differences within a group. Records persist across restarts; validation, duplicate feedback, CSRF protection, and group access checks remain active.

## Library behavior

- Filter by an authorized study group, refresh, and page through up to 24 resources at a time.
- Preview UTF-8 text/code as literal text, PDFs, and supported PNG/JPEG/GIF/WebP images. Large text above 2 MiB uses download instead. PDF display depends on the browser's PDF support; Download remains available.
- Download original file bytes with a safe original filename. Office documents and unsupported/active formats are download-only. The server derives safe inline types from the extension and byte signature rather than trusting stored MIME metadata.
- Downloads stream in bounded 64 KiB chunks. Protected single-byte range requests support PDF seeking and partial transfers; unsupported multipart ranges fall back to a full response.
- Missing, incomplete, unauthorized, or expired-session requests produce clear feedback. Account/group changes clear previews and ignore stale responses.

Material access is **group-scoped**. The #7 folder table and routes are preserved alongside the #12 material schema. Materials currently reference groups; linking uploads to destination folders remains part of the upload integration. Folder association, uploads (#8), and format/size validation before upload (#11) require the documented handoff to Anushree. The generated demo files let this PR be exercised without claiming those modules are complete. Once #6 merges, its dashboard Materials action should be wired to `/materials` and enabled in its capability list during integration; the direct library URL works independently now.

## Checks

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q server.py study_platform tests
node --check static/app.js
node --check static/folders.js
node --check static/materials.js
node --test tests/*.cjs
```

Node.js is required only for frontend tests and syntax checks. The Python suite dispatches actual HTTP handlers over in-memory connections with temporary SQLite databases; it needs no listening port. Frontend tests execute the actual JavaScript with a simulated DOM and fetch responses.

Local results: **75 Python tests** pass on Python 3.12 and 3.14; **30 JavaScript tests** pass. CI retains pinned actions and Python 3.11/3.12 coverage. Live HTTP integration checks pass on a loopback server. Interactive browser verification and remote CI remain pending your run/push.

## Issue documents

- [Manual checks and test evidence](docs/issue-12-test-results.md)
- [Step-by-step branch, commit, PR, and board guide](docs/issue-12-workflow.md)
- [PR description — closes #12 only](docs/issue-12-pr.md)
- [Shared authentication, authorization, and upload integration contract](docs/integration.md)
- [Merged #7 folder behavior and checks](docs/issue-7-test-results.md)
- [Earlier #5 review fixes](docs/pr23-review-fixes.md)
