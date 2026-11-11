# Unit Test Report

## 1. Overview

This report records the automated unit test results for the StudySpace application.

## 2. Test Environment

- Repository: Kr1491/SE-Mini-Project
- Branch: main
- Environment: Ubuntu on WSL
- Python framework: unittest
- JavaScript framework: Node.js built-in test runner
- Node.js version: v22.23.4

## 3. Test Execution Results

| Test category | Executed | Passed | Failed |
|---|---:|---:|---:|
| Python unit tests | 242 | 242 | 0 |
| JavaScript tests | 97 | 97 | 0 |
| Total | 339 | 339 | 0 |

## 4. Python Test Results

Command:

`python3 -m unittest discover -s tests -p "test_*.py" -v`

- Tests executed: 242
- Passed: 242
- Failed: 0
- Errors: 0
- Execution time during coverage run: 110.673 seconds

## 5. JavaScript Test Results

Command:

`node --test tests/*.cjs`

- Tests passed: 97
- Tests failed: 0
- Execution time: approximately 927.76 ms

## 6. JavaScript Syntax Validation

All 9 JavaScript files specified in the CI workflow passed `node --check`:

- static/results.js
- static/quiz-attempt.js
- static/memberships.js
- static/admin-users.js
- static/login.js
- static/app.js
- static/dashboard.js
- static/folders.js
- static/materials.js

## 7. Overall Result

All 339 executed automated tests passed successfully. No failures or errors were reported.

All 9 JavaScript syntax checks also completed successfully.

## 8. Notes

These results represent locally executed tests against the checked-out main branch. Passing automated tests does not mean that every manual test case in the Test Plan has been completed.

Code coverage and branch coverage are documented separately.
