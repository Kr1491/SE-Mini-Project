# Issue #21 — review and publication

Code branch: `test/21-security-verification`, integrated with main `53cc60a` and merged #17 results/performance. The saved stashes remain as backups; do not reapply the older prototypes over this work.

## Status

Local verification is complete: 242 Python tests on 3.12/3.14, 95 JavaScript tests, compilation/syntax/diff checks and three real Chrome flows pass. Findings, evidence and localhost scope are in [issue-21-security-review.md](issue-21-security-review.md). Deployed HTTPS is Not Applicable to this local environment and remains unverified.

Keep #21 **In review** while PR #40 is open; after successful checks and merge, the issue closes and can be moved to **Done**. GitHub Projects may require the final status update manually if no workflow is configured. No new issue or duplicate PR is needed.

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
node --check static/results.js
git diff --check
```

## Publish updates to the existing PR

Stage only the files in this change; leave unrelated planning/security drafts and `signin_dummy.txt` out. Review the diff, commit and push `test/21-security-verification` to update PR #40. Do not create a second PR for the same issue.

```bash
git diff --check
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
git push origin test/21-security-verification
gh pr checks 40 --repo Kr1491/SE-Mini-Project
```

Review `docs/issue-21-pr.md` and `docs/issue-21-security-review.md` with the code. The closing reference applies to the documented local scope; it does not claim HTTPS deployment was tested. After merge, restart any existing local server before checking the updated website.
