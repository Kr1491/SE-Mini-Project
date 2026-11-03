Verify the security of implemented login/session, role/group, Administrator, material and quiz/scoring endpoints, and fix findings reproduced during that review. The new regression suite checks real populated Student responses for password/answer-key omission and verifies that revoked write authority is enforced.

Restricted groups now require owner/Administrator approval rather than granting membership to any Student who knows an ID. The user confirmed this admission policy. Existing members retain access; existing groups migrate conservatively to approval-required, and new groups can explicitly allow open joining. The dashboard provides join-request and approval controls. Demo membership mutations are read-only to preserve fixed fixture identities.

Backup/recovery now rejects symlinks rather than dereferencing outside files, restricts backup/restored data to private POSIX permissions, and refuses shared restore parents before altering existing data. Group/folder/upload writes recheck current session/role/scope under their write transaction.

Validation: 231 Python tests pass on 3.12 and 3.14; 88 JavaScript tests pass. Compilation, syntax and diff checks pass. Real isolated Chrome flows verify restricted request/approval/resource access and quiz creation/publication/submission/scoring with repeat-safe receipts.

**Partial #21 sign-off:** the project is localhost-only, so deployed HTTPS is unverified. Final #17 result-history/performance checks await integration of PR #39. The report in docs/issue-21-security-review.md distinguishes executed checks, resolved findings and these remaining checks. This PR must not automatically close the overall issue.

Related to #21
