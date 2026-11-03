# Issue #21 — review and publication

Code branch: `test/21-security-verification`, based on main cae0402. The earlier security work is restored and reconciled with the real #14/#15/#16 schemas. The saved stashes remain as backups; do not blindly apply the older #16 sample draft or reapply the original #21 stash over this work.

## Status

Local verification/fixes are ready: 231 Python tests on 3.12/3.14, 88 JavaScript tests, compilation/syntax/diff checks and two real Chrome flows pass. The complete findings and limitations are in [issue-21-security-review.md](issue-21-security-review.md).

Keep #21 **In progress**. It is not fully Done: #17/PR #39 must be integrated and verified, and deployed HTTPS remains unverified because the project is localhost-only. A local hardening PR can be reviewed/merged without closing #21. The user authorized committing, pushing and opening a partial hardening PR. The commands below describe that publication workflow; the overall issue must remain open for the stated sign-off checks.

## Run the local changes

Stop earlier backend processes that use the same test database, including older previews on other ports. They retain their previous in-memory join/authorization code until restarted. Then in VS Code Terminal:

```bash
cd "/Users/krishnajha/Desktop/SE_MINI_PROJEC/SE-Mini-Project"
git switch test/21-security-verification
python3 server.py --database var/login-preview/accounts.db --storage var/login-preview/materials --port 8005
```

Open http://127.0.0.1:8005/login and use the local test accounts created earlier. In normal mode:

1. Instructor: choose Owner approval required or Open joining when creating a group. Group cards show their IDs/policy. Existing groups default to approval-required; previous members remain members.
2. Student without groups: enter a restricted group ID in Your join requests. It must remain Pending, and group materials/quizzes must remain denied.
3. Group owner or Administrator: review the request with Approve/Decline. Another Instructor must not review a foreign group's request.
4. Student: refresh the overview after approval; access should now work. Declining must leave access denied. Your request history must not expose other Students' requests or nonmember private group names.
5. Explicitly open groups allow direct joining. Read-only demo accounts cannot change membership; use the normal-mode test accounts for mutations.

The backend migration creates join_policy/membership-request tables. Back up an important database first. Existing data is retained; only the default admission behavior for future joins changes. This feature creates no default passwords or accounts.

## Backup/restore permissions

Use an owned private output/target directory. For the default local backup root:

```bash
mkdir -p .local-backups
chmod 700 .local-backups
python3 -m study_platform.recovery backup --database var/login-preview/accounts.db --storage var/login-preview/materials --output .local-backups
```

Private directories use 0700 and copied data 0600. Existing shared restore parents are refused rather than silently modified. Stop the app before a real restore.

## Checks

```bash
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
python3 -m compileall -q server.py study_platform tests
node --check static/memberships.js
node --check static/dashboard.js
node --check static/quiz-attempt.js
git diff --check
```

## Commit and create a partial hardening PR

```bash
git add .github/workflows/ci.yml README.md server.py static/dashboard.css static/dashboard.html static/dashboard.js static/memberships.js study_platform/db.py study_platform/security.py study_platform/memberships.py study_platform/dashboard.py study_platform/demo.py study_platform/folders.py study_platform/recovery.py tests/test_access.py tests/test_security_verification.py tests/test_membership_approval.py tests/test_memberships_frontend.cjs docs/integration.md docs/BACKUP_RECOVERY.md docs/issue-21-pr.md docs/issue-21-security-review.md docs/issue-21-workflow.md
git diff --cached --stat
git diff --cached --check
git commit -m "Verify local security and harden restricted group admission"
git push -u origin test/21-security-verification
gh pr create --repo Kr1491/SE-Mini-Project --base main --head test/21-security-verification --title "Verify local security and harden restricted group admission" --body-file docs/issue-21-pr.md --assignee Kr1491
```

Only the listed files belong in the commit; exclude unrelated planning/security drafts and signin_dummy.txt. The description references Related to #21 and deliberately does not close it. Remote CI/review follow the push. After #17 integration and a documented deployment/scope decision, execute the remaining acceptance checks before closing #21.
