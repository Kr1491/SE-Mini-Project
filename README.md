# StudySpace — role-specific dashboards

Issue **#6** adds separate Student, Instructor, and Administrator dashboard experiences on top of the merged #5 role-access foundation. The dashboard is the application landing page at `/` or `/dashboard`; the existing access/group-folder workspace remains at `/access`.

The change is independent of #7's review branch. If #7 is already present, its folder workspace is linked automatically; otherwise folders remain clearly unavailable. This PR does not implement group creation, uploads, material access, quizzes, results, or user-management operations.

## Run

Python 3.11+; no extra Python packages or frontend build step.

```bash
mkdir -p var
chmod 700 var
python3 server.py --demo
```

Open **http://127.0.0.1:8000**. Stop with Ctrl+C. Use `--port 8002` and the matching URL if another development server is using port 8000.

Demo accounts/groups are explicit local fixtures rather than credential-based login. Demo mode is loopback-only and uses `var/demo-access.db`; normal mode uses `var/issue5.db` and requires Jiya's verified login/session integration. Existing private-database and demo-fixture checks remain in force. No schema or data migration is introduced by #6.

## What each role sees

| Role | Summary | Navigation and tools |
|---|---|---|
| Student | Accessible groups and active study partners within those groups. | Study groups, learning tools, and available group folders. |
| Instructor | Owned group count and other groups joined. | Teaching groups, teaching tools, and permitted folder access. |
| Administrator | Active account, study group, and membership counts. | All groups, administration tools, and access checks. |

Counts and group names come from the database. The server derives the role from the current session; query parameters cannot request another user's or role's data. Missing/inactive/expired sessions are rejected, and group scope changes appear on refresh.

Not-yet-implemented tools show **Coming soon** without an action link. The page does not invent quiz/material counts or imply that future features are complete. Names are rendered as literal text. Dashboard and account refreshes discard stale responses, and failures clear the previous account's data.

Optional direct role pages `/dashboard/student`, `/dashboard/instructor`, and `/dashboard/administrator` require the matching authenticated role. Generic `/dashboard` opens the current account's dashboard. `/access` preserves the existing permission checks and, once #7 is merged, its folder UI.

## Try it

1. Choose Student, Instructor, then Administrator. Check that headings, summaries, navigation and tools change for each role.
2. Choose Student without groups. It should show a clear empty group state and no private group data.
3. Use Refresh overview and confirm the current account's data stays consistent.
4. Try another role's direct page: the backend must reject it.
5. If #7 is present, open Group folders and verify the existing folder workspace still works at `/access#folders-panel`.
6. Check a narrow browser width and the browser console.

## Checks and evidence

```bash
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
python3 -m compileall -q server.py study_platform tests
node --check static/app.js
node --check static/dashboard.js
```

The #5-based version passes **51 Python tests and 15 Node tests**. Compatibility with #7 was also tested: **67 Python tests and 25 Node tests pass** with both features present. Python suites pass locally on 3.12 and 3.14; the declared 3.11 floor is covered by the configured CI matrix. These results use real HTTP handlers/SQLite with in-memory connections and actual frontend scripts in a controlled DOM/fetch harness. A live browser/socket check and remote CI results remain pending.

## PR and integration

- [Issue #6 PR description](docs/issue-6-pr.md).
- [Issue #6 test results](docs/issue-6-test-results.md).
- [Issue #6 branch/PR/status workflow](docs/issue-6-workflow.md).
- [Integration contract](docs/integration.md).

Use `feat/6-role-dashboards` based on updated `main`. Its PR closes only #6. Keep #7's review branch and PR separate. All commits, pushes and PR creation are performed by Krishna.
