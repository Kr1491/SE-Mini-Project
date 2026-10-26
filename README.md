# StudySpace — study-group folders

Issue **#7** adds authorized folder listing and creation on top of the role-access foundation from #5. It includes the group picker, a folder creation form, validation, duplicate protection, and persistent SQLite storage.

This change does not implement role-specific dashboards (#6), material viewing/downloading (#12), registration/login (#3/#4), group creation (#9), membership management (#10), uploads (#8), or upload validation (#11). Those remain separate features and PRs.

## Run locally

Python 3.11+; no additional Python packages or frontend build step.

```bash
mkdir -p var
chmod 700 var
python3 server.py --demo
```

Open **http://127.0.0.1:8000**. Stop with **Ctrl+C**. If port 8000 is occupied, add `--port 8001` and open that port.

Explicit local demo mode uses sample accounts and groups rather than real registration/login. Demo user/group/membership fixtures must remain unchanged; newly created folders are normal persisted data and are retained on restart. Demo defaults to `var/demo-access.db`; normal mode defaults to `var/issue5.db`. Choose a fresh `--database` path if an earlier unmarked or conflicting fixture database is refused. No existing data is overwritten to repair fixtures.

POSIX databases use owner-only `0600` permissions in a private `0700` directory. The local demo is loopback-only; normal mode rejects demo-issued sessions. Real authentication must follow [the integration contract](docs/integration.md).

## Check folder creation

1. Select **Instructor** and find **Group folders** below the access checks.
2. Select **Software Engineering**, enter `Unit 1 notes`, and create the folder.
3. Refresh or restart the application: the folder remains in the same group.
4. Try the same name with different letter case: the API returns 409 and the form explains the duplicate.
5. Select another group: folders remain associated with their original group.
6. Select **Student**: group folders can be viewed, while the creation form is hidden and unauthorized API writes are rejected.
7. Select **Administrator**: creation is available in every group, including Private Research.
8. Select **Student without memberships**: the picker displays a clear no-groups state and creation stays unavailable.

Names are trimmed, normalized to Unicode NFC, and limited to 1–80 characters. Blank, non-text, control-character and hidden-formatting names are rejected. Duplicate names are compared using Unicode casefold within each group; the same name can exist in different groups. Names are displayed as text, not HTML. Creating a folder makes a database record; uploading/moving materials is separate work.

## Checks

```bash
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
python3 -m compileall -q server.py study_platform tests
node --check static/app.js
node --check static/folders.js
```

**51 Python tests pass on local Python 3.12 and 3.14, plus 15 Node frontend tests.** The suite includes existing #5 regressions and new #7 checks. CI runs the declared Python 3.11 floor alongside 3.12; remote results are pending a push. A live browser/socket check is still manual because this execution environment blocks TCP listeners. The frontend harness tests actual JavaScript with controlled DOM/fetch behavior.

## Files and PR

- `study_platform/folders.py`: authorized group/folder operations and name validation.
- `study_platform/db.py`: additive folder table with group-scoped unique normalized names.
- `server.py`: group picker and folder API routes; commits successful writes before responding.
- `static/folders.js`: folder UI with account/group request ordering and submission protection.
- `tests/test_folders.py` and `tests/test_folders.cjs`: feature regression coverage.
- [Issue #7 PR description](docs/issue-7-pr.md).
- [Issue #7 workflow](docs/issue-7-workflow.md).
- [Issue #7 validation](docs/issue-7-test-results.md).
- [Integration contract](docs/integration.md).

Issue #5 is still in review at preparation time. Start `feat/7-folder-creation` from updated `main` after #5 is merged, then apply only this patch. Its PR must contain **Closes #7** only. The generic access-verification page remains available to test permissions; it is not the separate role-specific dashboard feature.
