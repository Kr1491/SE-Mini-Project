# Issue #5: commands and board movement

This is one issue, one branch, one PR. Keep #6, #7 and #12 for later branches/PRs. All commit, push, PR and merge actions are performed by Krishna.

## When to move a card

| Status | Meaning for #5 | What you do |
|---|---|---|
| Backlog | Planned, still waiting for clarification/prerequisites. | Keep future work here until it can be prepared. |
| Ready | Acceptance criteria and interfaces are clear; you can begin. | Select #5 as your next task. |
| In progress | Implementing, testing or fixing #5. | Keep #5 here while checking the local code. |
| In review | The PR is open and ready for review. | Move #5 here after opening its PR; request review. |
| Done | Review/checks pass, changes are merged, and relevant behavior is verified. | Mark #5 Done after these conditions are satisfied. |

If review requests changes, return #5 to In progress, fix and push, then return it to In review. If waiting on authentication integration, record that dependency rather than claiming an unverified flow passed. A commit or push alone does not make an issue Done.

## 1. Prepare the actual repository

If the assistant could only prepare a temporary copy because the workspace folder was renamed, apply that prepared copy using the supplied `apply_issue5.py` command first. That script verifies the expected Git state, backs up the original implementation and staged diff outside the repo, replaces only the issue files, and unstages the previous combined change. It does not commit, push, or open a PR. Read its output before continuing.

If the assistant already applied the changes in the correctly opened workspace, skip the script.

## 2. Create the #5 branch and run checks

From the actual repository (the currently discovered folder is shown below):

```bash
cd "/Users/krishnajha/Desktop/SE_MINI_PROJEC/SE-Mini-Project"
git switch -c feat/5-role-access
python3 -m unittest discover -s tests -v
python3 server.py --demo
```

If `feat/5-role-access` already exists, use `git switch feat/5-role-access` instead of creating it again. Stop any earlier running copy of the full-demo server with Ctrl+C before starting this version.

Open http://127.0.0.1:8000 and follow the README checks. Press Ctrl+C after checking the browser.

## 3. Stage only #5 and its necessary foundation

```bash
git add .gitignore README.md server.py study_platform static tests/test_access.py .github/workflows/ci.yml docs/integration.md docs/issue-5-pr.md docs/issue-5-test-results.md docs/issue-5-workflow.md
git diff --cached --stat
git diff --cached --check
```

The staged change should contain role access and its tests/demo/foundation. Shared planning files (`plan.md`, allocation CSV, and sprint plan) can remain untracked for a separate documentation change. The old combined `tests/test_sprint1.py` and four-issue PR description should not appear in this PR.

## 4. Commit and push your branch

Only after reviewing the staged file list and checks:

```bash
git commit -m "Implement role-based access control"
git push -u origin feat/5-role-access
```

If Git asks you to authenticate, complete your own GitHub sign-in and retry the push. Pushing the branch does not merge it into `main`.

## 5. Open the PR and move #5 to In review

Open:

https://github.com/Kr1491/SE-Mini-Project/compare/main...feat/5-role-access?expand=1

Use base `main`, compare `feat/5-role-access`, and title **Implement role-based access control**. Copy [issue-5-pr.md](issue-5-pr.md) into the description. It links only `Closes #5`.

Request a teammate's review, wait for the required checks, and address feedback. Keep #6, #7 and #12 outside this PR.

## 6. After review, merge and verification

Merge the PR when ready, verify the feature in the integrated application, and set #5 to Done. GitHub may close the linked issue automatically when merging; still check the project card and actual verification.

Following the revised priority order, start High-priority #7 from updated `main`:

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/7-folder-creation
```

Move #7 to Ready when its criteria/dependencies are clear, then In progress when you begin. Apply only its dedicated folder change, following issue-7-workflow.md. Continue with High-priority #12 and then Medium-priority #6, keeping each issue on its own branch/PR. Do not restore the full four-issue snapshot over `main` wholesale.
