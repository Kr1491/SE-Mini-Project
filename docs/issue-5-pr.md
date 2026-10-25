Implements server-side role-based access for Student, Instructor, and Administrator accounts, including group-scoped authorization, active/expiring sessions, and CSRF checks for authenticated JSON mutations. Includes the minimal Python/SQLite foundation and an explicit local permission-verification demo so the policy can be reviewed before real authentication is integrated.

Closes #5

Validation:
- 35 Python integration/regression tests pass locally on Python 3.12 and 3.14; five Node frontend/contrast tests pass.
- CI runs Python 3.11 and 3.12, and uses pinned full commit SHAs for both GitHub Actions. Its remote results remain pending the update being pushed.
- Python compilation and JavaScript syntax checks pass.
- Live TCP server and browser checks remain manual because this execution environment blocks socket binding.
- GitHub Actions checks are configured; the remote run is pending the branch being pushed.

The sample-account selector requires explicit local `--demo` mode and is not registration or credential-based login. Dashboards (#6), folders (#7), and material access (#12) remain separate changes. The real login/session integration with Jiya's module must also be verified.

Review follow-up: addresses all 10 supplied findings, including fixture isolation, committed session creation, frontend response ordering, text contrast, database invariants/permissions, pinned Actions, IPv6 rejection, and Python-floor CI coverage. Also prevents demo sessions being reused in normal mode and rejects malformed group IDs/CSRF tokens without server errors. See docs/pr23-review-fixes.md.
