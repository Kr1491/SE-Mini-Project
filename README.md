# StudySpace — issue #5: role-based access control

This change implements **issue #5 only**, with the shared Python/SQLite foundation needed to run and test permissions. The generic access-verification page lets you check server-side permissions for students, instructors, and administrators.

Dashboard implementation (#6), folder creation (#7), and material viewing/downloading (#12) belong to later branches and PRs. Registration/login (#3/#4), group creation (#9), membership management (#10), uploads (#8), and file validation (#11) remain their assigned owners' integration work.

## Run

Python 3.11+ is required. No additional Python packages or frontend build step are needed.

```bash
mkdir -p var
chmod 700 var
python3 server.py --demo
```

Open **http://127.0.0.1:8000**. Stop with **Ctrl+C**. If port 8000 is occupied, add `--port 8001` and open the matching address.

Explicit `--demo` mode seeds sample accounts/groups and enables a local sample-account selector. It is an authorization test fixture, not registration or credential-based login. It is limited to loopback addresses. The demo database defaults to ignored `var/demo-access.db`; normal mode defaults to `var/issue5.db`. A demo database must be empty on first use and contain only unchanged fixtures on reuse. Existing databases with fixture conflicts are rejected, including legacy demo databases without the fixture marker; choose a fresh path rather than overwriting data.

On POSIX systems, a new database is created with permissions `0600` inside a private `0700` directory. Existing database files are tightened to `0600`; existing shared parent directories are refused with instructions to use a private directory. Demo sessions are tagged and rejected in normal mode.

Without `--demo`, the sample selector and its endpoint are disabled. Jiya's real login module must verify credentials and issue a session using the helper documented in [integration.md](docs/integration.md).

## Verify #5 in your browser

1. Select **Student**: instructor, quiz-creation, and administrator probes must return **403**; sample group 1 is allowed and group 3 denied.
2. Select **Instructor**: instructor/quiz-authoring probes and management of group 1 are allowed; administrator access and group 3 are denied.
3. Select **Administrator**: all displayed probes are allowed.
4. Select **Student without memberships**: access to sample groups 1 and 3 is denied.
5. Switch accounts and verify permissions change immediately.

A permission probe only verifies authorization. It does not create a quiz, manage users, create folders, or serve a dashboard.

## Automated checks

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q server.py study_platform tests
node --check static/app.js
node --test tests/test_frontend.cjs
```

The test suite uses real HTTP parsing/dispatch, SQLite, and in-memory connections. It does not need a listening port. Node.js is needed only for the JavaScript syntax check, not to run the application.

All **35 Python tests and five frontend tests pass** in the review-fix copy. Python tests were executed on 3.12 and 3.14 locally; CI is configured to test the declared 3.11 floor alongside 3.12, and its remote result is pending your push. A live server/browser check is pending because this execution environment blocks socket binding. GitHub Actions includes the same checks; its remote result is pending your push.

## Review and next steps

- [PR #23 review findings and responses](docs/pr23-review-fixes.md).
- [Issue #5 PR description](docs/issue-5-pr.md).
- [Test results](docs/issue-5-test-results.md).
- [Commands and board status guide](docs/issue-5-workflow.md).
- [Authentication and authorization integration contract](docs/integration.md).

Open a PR with base `main` and compare `feat/5-role-access`, linking only **Closes #5**. After review, merge, and verification, start #6 on a fresh branch from updated `main`.
