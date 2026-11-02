# Issue #16 — preview and PR commands

The real #13/#14/#15 code is merged. #16 now extends that implementation on `feat/16-quiz-submission`; the old sample draft was not restored. Keep #16 **In progress** during local review. The #21 security/admission work remains separately stashed. No commit, push, PR or merge for #16 has been performed by the assistant.

## Run and try it

```bash
cd "/Users/krishnajha/Desktop/SE_MINI_PROJEC/SE-Mini-Project"
git switch feat/16-quiz-submission
python3 server.py --database var/login-preview/accounts.db --storage var/login-preview/materials --port 8007
```

Use http://127.0.0.1:8007/login and the local test credentials supplied earlier. Stop any older server if you want to reuse its port; it must be restarted to load the new backend. The normal-mode test database persists your quizzes and results.

1. Sign in as **Instructor**. Open Create quizzes; choose Software Engineering or Database Systems (groups shared with the local Student), create MCQs and publish.
2. Sign out, sign in as **Student**, open Available quizzes, then Start Quiz.
3. Choose answers, Submit answers, review the unanswered warning if applicable, and Confirm submission. Correct = 1 point; wrong/unanswered = 0. The saved score appears and answers lock.
4. Use Back to quizzes to leave the receipt. Results history/performance remains #17. Follow [the additional checks](issue-16-test-results.md).

The feature creates no default accounts or quizzes. In explicit --demo mode, existing sample accounts can also use the actual creation/publish/attempt workflow, but fixtures are still for local preview only.

## Checks

```bash
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
python3 -m compileall -q server.py study_platform tests
node --check static/quiz-attempt.js
node --check static/dashboard.js
git diff --check
```

Local results: 199 Python tests and 81 JavaScript tests pass, with a real Chrome end-to-end flow. Python 3.11 runs in the configured remote CI after push.

## Commit, push and create a PR

```bash
git add .github/workflows/ci.yml README.md server.py study_platform/db.py study_platform/quizzes.py study_platform/quiz_scoring.py study_platform/dashboard.py static/dashboard.html static/dashboard.css static/dashboard.js static/quiz-attempt.js tests/test_dashboard.py tests/test_quiz_scoring.py tests/test_quiz_attempt_frontend.cjs docs/integration.md docs/issue-16-pr.md docs/issue-16-integration.md docs/issue-16-test-results.md docs/issue-16-workflow.md
git diff --cached --stat
git diff --cached --check
git commit -m "Implement quiz submission and server-side scoring"
git push -u origin feat/16-quiz-submission
gh pr create --repo Kr1491/SE-Mini-Project --base main --head feat/16-quiz-submission --title "Implement quiz submission and scoring" --body-file docs/issue-16-pr.md --assignee Kr1491
```

Stage only the files above; existing planning/security documents and signin_dummy.txt are unrelated. Review the staged changes. The PR closes **#16 only**. Once open, move #16 to **In review**. Review/CI/merge and integrated verification must finish before Done. Let Anushree use [the scoring data contract](issue-16-integration.md) for #17 after the change is integrated.
