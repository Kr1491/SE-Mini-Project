# Issue #7 — branch, PR, and board workflow

#7 is High priority (P0), three story points, assigned to Krishna in Sprint 1. #6 is Medium priority; the revised sequence is **#7, then #12, then #6**, with each change developed on its own branch and PR.

## While #5 is still in review

Keep #5 in **In review**. #7 can be **In progress** while its draft is prepared/tested separately. Do not apply #7 changes to `feat/5-role-access`, because that would add a second issue to PR #23.

The draft was prepared against #5 commit `2729193`. If #5 changes again before merge, re-check the patch against the final merged version and adapt it rather than forcing a conflicting patch.

## After #5 is reviewed, merged, and verified

From the actual repository:

```bash
cd "/Users/krishnajha/Desktop/SE_MINI_PROJEC/SE-Mini-Project"
git switch main
git pull --ff-only origin main
git switch -c feat/7-folder-creation
```

Then run the supplied `apply_issue7.py` command. It requires the new #7 branch, a clean tracked state based on updated main/origin-main, and the #5 foundation. It checks the patch before applying. It does not stage, commit, push, open a PR, merge, or change your #5 branch.

## Check and run the feature

```bash
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
mkdir -p var
chmod 700 var
python3 server.py --demo
```

Open http://127.0.0.1:8000 and follow the README/manual checklist. Stop with Ctrl+C.

## Stage, inspect, commit, push

```bash
git add server.py study_platform/db.py study_platform/folders.py static .github/workflows/ci.yml tests/test_access.py tests/test_folders.py tests/test_folders.cjs README.md docs/integration.md docs/issue-5-workflow.md docs/issue-7-pr.md docs/issue-7-test-results.md docs/issue-7-workflow.md
git diff --cached --stat
git diff --cached --check
git commit -m "Implement study group folder creation"
git push -u origin feat/7-folder-creation
```

## Create the PR

Use base `main`, compare `feat/7-folder-creation`, title **Implement study group folder creation**, and the description from [issue-7-pr.md](issue-7-pr.md). It closes only #7.

```bash
gh pr create --repo Kr1491/SE-Mini-Project --base main --head feat/7-folder-creation --title "Implement study group folder creation" --body-file docs/issue-7-pr.md
```

Move #7 to **In review** once its PR is open. Address requested changes on the same branch. Mark it **Done** after review/checks, merge, and relevant verification. Begin #12 from freshly updated main after its prerequisites are available.

## Status meanings

| Status | When |
|---|---|
| Backlog | Planned work awaiting preparation/prerequisites. |
| Ready | Criteria and interfaces are clear, and the task can be started. |
| In progress | Coding, applying the draft, testing, or fixing it. |
| In review | PR is open for review. |
| Done | Review/checks pass, code is merged, and relevant behavior is verified. |
