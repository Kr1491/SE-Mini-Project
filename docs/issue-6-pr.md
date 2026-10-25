Builds role-specific Student, Instructor and Administrator dashboards with database-backed summaries, scoped study groups, role-appropriate navigation and feature availability. The landing page opens the current account's dashboard; direct role pages and APIs require the matching authenticated role.

Closes #6

The UI safely renders profile/group names, clears stale private data on failure, and ignores old refresh responses after account switching. Future tools are labelled Coming soon without dead links or invented counts. Existing access checks remain at /access, and the #7 folder workspace is linked only when its implementation is present.

Validation:
- #5-only base: 51 Python tests and 15 Node frontend tests pass.
- #7 compatibility: 67 Python tests and 25 Node frontend tests pass.
- Python suites pass locally on Python 3.12 and 3.14; compilation and JavaScript syntax checks pass.
- CI retains the Python 3.11/3.12 matrix and pinned Actions; remote runs are pending the push.
- Live-browser/TCP verification remains manual due to the execution environment's socket-binding restriction.

This PR depends on the merged #5 foundation and is independent of #7's review. It adds no registration/login, upload/material, quiz, or administrator user-management implementation.
