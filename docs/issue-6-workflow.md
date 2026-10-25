# Issue #6 — branch, PR and board workflow

#6 is Medium priority (P1), three story points, assigned to Krishna in Sprint 1. The user explicitly selected it as the next task while #7 remains in review. Keep the two changes on separate branches and PRs.

## Start from main

#5 is merged. #6 does not require #7 to merge first:

```bash
cd "/Users/krishnajha/Desktop/SE_MINI_PROJEC/SE-Mini-Project"
git switch main
git pull --ff-only origin main
git switch -c feat/6-role-dashboards
```

Run the supplied `apply_issue6.py` command next. It requires the #6 branch based on updated main/origin-main, checks for the #5 foundation and a clean tracked state, and chooses the patch variant matching whether #7 is already present. It checks the patch before applying and does not stage, commit, push or create a PR. If newer overlapping changes cause a patch conflict, stop and refresh the preparation against the new main rather than forcing it.

## Test and preview

```bash
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
mkdir -p var
chmod 700 var
python3 server.py --demo
```

Open http://127.0.0.1:8000 and follow the README. Stop with Ctrl+C. If another development server is running, use `--port 8002` and open the matching port.

## Stage, inspect, commit and push

```bash
git add .github/workflows/ci.yml README.md server.py study_platform/dashboard.py static/dashboard.html static/dashboard.css static/dashboard.js tests/test_access.py tests/test_dashboard.py tests/test_dashboard.cjs docs/integration.md docs/issue-6-pr.md docs/issue-6-test-results.md docs/issue-6-workflow.md
git diff --cached --stat
git diff --cached --check
git commit -m "Build role-specific dashboards"
git push -u origin feat/6-role-dashboards
```

## Create the PR

```bash
gh pr create --repo Kr1491/SE-Mini-Project --base main --head feat/6-role-dashboards --title "Build role-specific dashboards" --body-file docs/issue-6-pr.md
```

This description closes only #6. Request review and check CI. Changes made in response to review stay on the same #6 branch/PR. If another PR changes shared files before merge, update this branch against main and verify the combined behavior before merging.

## Board status

- **Ready:** criteria and prerequisites are clear and the task can begin.
- **In progress:** prepare/apply the dashboard code, test it and fix defects. Keep #6 here now.
- **In review:** the separate #6 PR is open for review.
- **Done:** review and required checks pass, code is merged and the relevant behavior is verified.

Keep #7 in its actual review state and use its own branch for folder review fixes. A dashboard PR does not close #7 or #12.
