# Issue #12 — commands and board flow

Keep #6 and #7 **In review**. Move #12 to **In progress** while its code is being prepared/applied/tested. Ready means it is understood and waiting to be picked up; do not move started work back to Ready merely because commands have not been run.

## Start a separate branch and apply the prepared code

The project folder was renamed, while this session's write permissions still point at its old name. The prepared code lives in `/private/tmp/se-issue12-fv3ek4i8`. Run these commands in your own Terminal:

```bash
cd "/Users/krishnajha/Desktop/SE_MINI_PROJEC/SE-Mini-Project"
git status --short --branch
git switch main
git pull --ff-only origin main
git switch -c feat/12-material-access
python3 /private/tmp/se-issue12-fv3ek4i8/apply_issue12.py
```

The apply script checks that it is on the fresh #12 branch based on updated main, verifies expected source-file hashes, refuses tracked/staged changes or conflicting new files, and checks the complete patch before applying. It never commits, pushes, opens a PR, or changes the #6/#7 branches. If any command fails, stop and share its output; do not force/reset anything. If main has changed in the same files after this preparation, refresh the patch against that main first.

## Verify locally

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q server.py study_platform tests
node --check static/app.js
node --check static/materials.js
node --test tests/*.cjs
python3 server.py --demo --port 8003
```

Open `http://127.0.0.1:8003/materials` and follow [the manual checks](issue-12-test-results.md). Use Ctrl+C to stop the server. Node is only needed for frontend checks, not the application. Use another unused port if needed. These checks must pass before continuing.

## Stage only #12, commit, push, and open the PR

```bash
git add .github/workflows/ci.yml README.md server.py study_platform/db.py study_platform/materials.py study_platform/material_fixtures.py static/index.html static/materials.html static/materials.css static/materials.js tests/test_access.py tests/test_materials.py tests/test_materials_frontend.cjs docs/integration.md docs/issue-12-pr.md docs/issue-12-test-results.md docs/issue-12-workflow.md
git diff --cached --stat
git diff --cached --check
git commit -m "Implement material viewing and downloading"
git push -u origin feat/12-material-access
gh pr create --repo Kr1491/SE-Mini-Project --base main --head feat/12-material-access --title "Implement material viewing and downloading" --body-file docs/issue-12-pr.md
```

The tracked source and new #12 docs are staged explicitly. Existing untracked planning files remain outside this commit. Review the staged diff before committing. Keep the PR base repository **Kr1491/SE-Mini-Project**, base branch **main**, compare branch **feat/12-material-access**. Its description closes **#12 only**. Creating a PR does not merge it; owning the repository does not bypass the branch/PR flow.

If the GitHub CLI is unavailable, after pushing open the repository's Pull requests tab → New pull request. Select the same base and compare branches, paste `docs/issue-12-pr.md`, and create the PR.

## Review and completion

1. PR open → move #12 to **In review** and request a teammate's review manually. Keep #6/#7 in their existing review states.
2. Fix review findings on this same branch, test, commit, and push; the same PR updates. A review comment does not require creating another backlog issue.
3. Teammate reviews and CI passes → merge the #12 PR when ready. A PR being open or merely approved does not mean the issue is done.
4. Verify the merged behavior on main, then move #12 to **Done** if project automation has not already done so. `Closes #12` closes the linked issue when merged into the default branch; board automation depends on the project's configured workflows.
5. Start the next issue from updated main on its own branch. Several PRs can remain In review while you work on one new issue In progress.

The assistant has not staged, committed, pushed, opened, or merged anything in your repository.
