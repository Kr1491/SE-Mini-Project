# Issue #18 — verification

Base: origin/main at 2a4e175. Branch: feat/18-admin-user-management. Issue #16 remains paused separately; no quiz code is included.

## Results

- Python 3.12 and 3.14: **143 tests pass** on each interpreter (124 base tests, 18 management tests, and one dashboard integration test).
- Node.js: **65 tests pass** (52 base tests, 12 management-interface tests, and one dashboard link test).
- Python compileall, syntax checks for admin-users.js/dashboard.js and git diff --check pass.
- A real isolated Chrome flow passed login as Administrator → dashboard management link → account list → review before saving → role change → suspension → filtering → page reload with saved values. Server-side checks confirmed the saved version/state, session deletion and two audit records. Direct instructor requests to the page and listing API returned 403.
- The desktop layout was visually checked. Narrow-screen wrapping is implemented, but interactive mobile/assistive-technology checks remain manual. GitHub CI retains Python 3.11/3.12 and pinned actions; no new remote CI result is claimed before push.

## Acceptance coverage

| Requirement | Evidence |
|---|---|
| Administrators view users and roles | Guarded page/API, safe paginated listing, role/access filters and name/email search; no passwords/hashes/session tokens returned. |
| Administrators update roles and access | Validated update API and confirmation UI; unsupported fields/types/roles rejected; normal-mode writes persist. |
| Changes are saved and enforced next request | Revoked session tokens return 401; fresh sessions obtain the updated role permissions; suspended/reactivated accounts cannot reuse pre-change tokens. Reinitialization preserves updates. |
| Non-administrators cannot manage users | Anonymous 401 and student/instructor 403 checks for page, listing and edits; role/active state rechecked inside the write transaction. |

Additional checks cover CSRF, self-demotion/suspension, stale-version conflicts, no-op edits, nonexistent/oversized IDs, literal SQL search strings and HTML-like names, audit rollback, commit-before-response, concurrent mutual demotion, read-only demo integrity and additive legacy-user migration. Frontend checks cover own-account/read-only controls, explicit confirmation/cancel, duplicate requests, stale search responses, pagination, version-conflict refresh and private-data clearing after 401/403.

## Manual review

1. Start normal mode against a local test database with a registered Administrator; sign in and open Users and permissions.
2. Confirm names/emails/roles/access and role-permission guides. Search and change role/access filters; page through results if needed.
3. Change a test student's role. Verify nothing is written until Confirm change. The affected session must stop working; a fresh login must get the new role. Restore the test role afterward if desired.
4. Suspend then reactivate another test account. Its old token must remain invalid; after reactivation it can log in again with its existing password.
5. Your own controls must be disabled. Direct student/instructor requests to /admin/users or its API must be denied.
6. In --demo mode, the sample Administrator can inspect the list, but edits are disabled and the API rejects them without changing fixture records.
7. Check mobile width, keyboard/Tab navigation, Escape/Cancel confirmation and errors. Put #18 In review once its PR is open; Done follows review, passing CI, merge and verification.

All mutation tests used temporary databases and accounts. Existing local test users were not changed by the tests.
