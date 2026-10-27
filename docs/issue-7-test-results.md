# Issue #7 verification — 25 October 2026

Current route note: with dashboard #6, `/` is the dashboard; the existing folder/access workspace is at `/access`, and the material library remains at `/materials`. Earlier commands/results below describe that issue's preparation.

Executed in the isolated #7 preparation copy based on issue #5 commit `2729193`:

| Check | Result |
|---|---|
| Python tests, local Python 3.14 | 51 passed |
| Python tests, local Python 3.12 | 51 passed |
| Node frontend tests | 15 passed |
| Python compilation | Passed |
| JavaScript syntax, app.js and folders.js | Passed |

The total includes all existing #5 regressions plus 16 new backend checks and 10 new frontend checks. They exercise authorization, correct group association, persistence after reinitialization/session changes, Unicode normalization/casefold duplicates, blank/type/control/length validation, CSRF, missing/oversized group IDs, SQL/HTML-like names, foreign keys, concurrent duplicates, and commit-before-response.

Frontend checks cover real form requests and CSRF headers, read-only/empty states, stale group/account responses, duplicate errors, repeated submissions, successful creation with a failed refresh, safe text rendering, and integration of the folder module with the existing access application.

The tests use real HTTP handlers with in-memory connections and real temporary SQLite databases; frontend tests use the actual scripts in a controlled DOM/fetch harness. They do not claim a live browser, TCP-listener, or remote CI result. The Python 3.11 job will run in GitHub Actions after the PR branch is pushed.

## Manual check before completion

- [ ] #5 is merged and #7 is on its own branch based on updated main.
- [ ] Run `python3 server.py --demo` in your own Terminal; open http://127.0.0.1:8000.
- [ ] Instructor can create in an owned group; blank/duplicate names show useful errors.
- [ ] Refresh/restart keeps the folder in the correct group.
- [ ] Student can read permitted groups but cannot create.
- [ ] Administrator can create in any group; nonmembers see no group folders.
- [ ] Account/group switching does not display the previous selection's data.
- [ ] Layout and form work at a narrow window width; browser console has no application errors.
- [ ] PR checks/review pass, merge completes, and the integrated feature is verified before #7 becomes Done.
