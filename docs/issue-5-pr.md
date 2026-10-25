Implements server-side role-based access for Student, Instructor, and Administrator accounts, including group-scoped authorization, active/expiring sessions, and CSRF checks for authenticated JSON mutations. Includes the minimal Python/SQLite foundation and an explicit local permission-verification demo so the policy can be reviewed before real authentication is integrated.

Closes #5

Validation:
- 18 automated HTTP-handler/SQLite integration tests pass in the preparation copy.
- Python compilation and JavaScript syntax checks pass.
- Live TCP server and browser checks remain manual because this execution environment blocks socket binding.
- GitHub Actions checks are configured; the remote run is pending the branch being pushed.

The sample-account selector requires explicit local `--demo` mode and is not registration or credential-based login. Dashboards (#6), folders (#7), and material access (#12) remain separate changes. The real login/session integration with Jiya's module must also be verified.
