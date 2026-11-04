Verify the security of implemented login/session, role/group, Administrator, material and quiz/scoring endpoints, and fix findings reproduced during that review. The new regression suite checks real populated Student responses for password/answer-key omission and verifies that revoked write authority is enforced.

Restricted groups now require owner/Administrator approval rather than granting membership to any Student who knows an ID. The user confirmed this admission policy. Existing members retain access; existing groups migrate conservatively to approval-required, and new groups can explicitly allow open joining. The dashboard provides join-request and approval controls. Demo membership mutations are read-only to preserve fixed fixture identities.

Backup/recovery now rejects symlinks rather than dereferencing outside files, restricts backup/restored data to private POSIX permissions, and refuses shared restore parents before altering existing data. Group/folder/upload writes recheck current session/role/scope under their write transaction.

Validation: 242 Python tests pass on 3.12 and 3.14; 95 JavaScript tests pass. Compilation, syntax and diff checks pass. Real isolated Chrome flows verify restricted request/approval/resource access quiz creation/publication/submission/scoring with repeat-safe receipts, and Student history/Instructor managed-group performance.

The merged #17 results/performance routes are now included in the security matrices and populated-response checks. Tests cover Student identity isolation, staff group restrictions, role/status/membership revocation, answer-key/credential omission and stale UI clearing.

**Scope:** the user confirmed localhost-only development. All applicable local checks are complete. Deployed HTTPS is **Not Applicable to the current environment and remains unverified**, rather than being marked passed. An actual deployment must separately verify TLS and cookie behavior. Findings, evidence and this scope decision are recorded in `docs/issue-21-security-review.md`.

Closes #21
