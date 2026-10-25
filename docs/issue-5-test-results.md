# Issue #5 verification — 25 October 2026

Executed in the isolated issue #5 preparation copy:

```text
python3 -m unittest discover -s tests -v
Ran 18 tests
OK

python3 -m compileall -q server.py study_platform tests
PASS

node --check static/app.js
PASS
```

The tests exercise real HTTP request parsing/dispatch using in-memory connections and real temporary SQLite databases. They cover:

- Anonymous, forged, expired, and inactive-user session rejection.
- Permission mapping and role-specific authorization for all three roles.
- Student denial for instructor, quiz-authoring and administrator probes.
- Instructor authoring access with administrator denial.
- Administrator access across groups.
- Membership/ownership checks and denial of other groups' resources.
- Group-management permission plus ownership.
- Immediate effect of role changes and membership revocation.
- Rejection of client-supplied user IDs/roles as authority.
- HttpOnly/SameSite cookie flags and token hashing.
- Revocation of the previous demo session when switching accounts.
- CSRF and permission checks for JSON requests.
- Normal-mode authentication helper with demo endpoint disabled.
- Invalid JSON/permission handling and static asset delivery.
- Absence of dashboard, folder-creation and material-view/download implementations in this issue's scope.

A listening-server attempt was blocked by the execution environment (`PermissionError` on TCP socket binding). Live browser behavior and the remote GitHub Actions run are not claimed as passing.

Manual checklist before treating #5 as Done:

- [ ] Restart with `python3 server.py --demo` in your Terminal.
- [ ] Student: instructor/admin/quiz-authoring probes deny access; group 1 allowed, group 3 denied.
- [ ] Instructor: authoring/group-1 management allowed, administrator/group-3 access denied.
- [ ] Administrator: displayed probes allowed.
- [ ] Nonmember: group probes denied.
- [ ] Switching accounts updates permissions correctly; browser console has no application errors.
- [ ] Review, required CI checks, and merge are complete.
- [ ] Verify real login/session integration when Jiya's module is available; record any pending integration explicitly.


## PR #23 review follow-up — 25 October 2026

Executed in the isolated review-fix copy:

- `python3 -m unittest discover -s tests -v`: **35 passed** (Python 3.14).
- `/opt/homebrew/bin/python3.12 -m unittest discover -s tests -v`: **35 passed**.
- `node --test tests/test_frontend.cjs`: **5 passed**, covering delayed initialization, both probe response orderings, account switching with a pending probe, and secondary-text contrast.
- Python compilation and JavaScript syntax checks pass.

The new backend cases cover fixture conflicts, runtime fixture revalidation, dedicated demo reuse, non-null session keys and migration, private file/directory permissions, rejection of a database symlink, explicit IPv6 rejection, session commit-before-response, demo-mode session isolation, large group IDs, and non-ASCII CSRF tokens.

Measured contrast: `.intro` and footer are **6.14:1** against the page background; `.muted` is **6.56:1** against its white panel. All exceed 4.5:1 for normal text. The frontend tests use the actual stylesheet values and the relative-luminance formula.

CI is configured for Python **3.11 and 3.12** with pinned Actions. Python 3.11 is unavailable locally, so its result is pending the GitHub run. The frontend tests execute the actual script with a controlled DOM/fetch harness; they do not claim a live-browser visual check. Live TCP/browser verification remains pending due to the execution environment's socket-binding restriction.
