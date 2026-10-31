# Issue #18 — local preview, commit and PR

The code is on **feat/18-admin-user-management**, created from latest main. It is separate from the paused #16 changes. Keep #18 **In progress** while testing. Publish this branch through its own PR linked to #18. The commands below describe the same commit/push/PR workflow authorized by the user.

## Preview with the local test accounts

Run in your VS Code Terminal:

```bash
cd "/Users/krishnajha/Desktop/SE_MINI_PROJEC/SE-Mini-Project"
git switch feat/18-admin-user-management
python3 server.py --database var/login-preview/accounts.db --storage var/login-preview/materials --port 8006
```

Open http://127.0.0.1:8006/login and sign in using the local test Administrator account created earlier. If currently signed in as another role, use Sign out first. From the Administrator dashboard, open Users and permissions; the direct page is /admin/users. If port 8006 is occupied, select another port and use that address. Stop with Ctrl+C.

Role/access changes on this preview persist in the selected test database and sign the affected user out. Your own role/status controls are disabled. No accounts, passwords or default administrator credentials are created by this feature. To use a different real database, supply its path instead.

For inspection only, run `python3 server.py --demo --port 8007`, select the sample Administrator and open the same tool. Demo accounts are read-only to preserve their fixed identities. Use normal-mode test accounts for actual edits.

## Checks

```bash
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
python3 -m compileall -q server.py study_platform tests
node --check static/admin-users.js
node --check static/dashboard.js
git diff --check
```

Follow [the manual review steps](issue-18-test-results.md). Local automated results are 143 Python tests and 65 JavaScript tests passing, plus the real browser/HTTP flow described there.

## Commit, push and create the PR

Stage only this feature and its documentation:

```bash
git add .github/workflows/ci.yml README.md server.py study_platform/db.py study_platform/admin_users.py study_platform/dashboard.py static/admin-users.html static/admin-users.css static/admin-users.js static/dashboard.js tests/test_admin_users.py tests/test_admin_users_frontend.cjs tests/test_dashboard.py tests/test_dashboard.cjs docs/integration.md docs/issue-18-pr.md docs/issue-18-test-results.md docs/issue-18-workflow.md
git diff --cached --stat
git diff --cached --check
git commit -m "Implement administrator user and permission management"
git push -u origin feat/18-admin-user-management
gh pr create --repo Kr1491/SE-Mini-Project --base main --head feat/18-admin-user-management --title "Implement administrator user and permission management" --body-file docs/issue-18-pr.md --assignee Kr1491
```

Existing untracked planning/security documents and signin_dummy.txt are outside this commit. If any command fails, stop and inspect its output rather than forcing it. The PR links **Closes #18** only. Move #18 to **In review** after the PR opens. Review findings stay on this branch/PR; mark Done after review, passing CI, merge and verification.
