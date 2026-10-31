Administrators can now open Users and permissions from their dashboard to search/filter registered accounts, inspect role capabilities, and change another user's role or active/suspended status after confirmation. Students, instructors and anonymous requests are denied on both the page and API. Responses omit passwords, password hashes and session data.

Role/status edits are saved atomically, increment an account version, revoke the affected user's sessions, and record the actor, prior/new state and UTC timestamp in a private database audit table. Changes therefore apply to the next protected request; reactivation does not revive old tokens. Stale edits return 409, and administrators cannot suspend or demote themselves. Concurrent administrator changes preserve an active administrator.

The schema update adds users.access_version and the audit table without replacing account data. Permissions use the existing role mapping; this does not add arbitrary per-user grants or transfer group ownership. Explicit demo fixtures are read-only so role/status editing cannot invalidate the existing sample-account selector. Real edits use normal mode with registered/local test accounts.

Validation: 143 Python tests pass on 3.12 and 3.14; 65 JavaScript tests pass. Compilation, JavaScript syntax and diff checks pass. A real isolated Chrome flow verified the dashboard action, confirmation before edits, role change, suspension, filtering and persistence after reload; HTTP checks also denied direct instructor access. Audit records and affected-session revocation were verified against the test database. Python 3.11 remains configured in CI; remote CI and review follow the user's push.

Closes #18
