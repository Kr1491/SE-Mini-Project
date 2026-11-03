# Issue #21 — local security verification and remediation

Review resumed **3 November 2026** against merged main **cae0402**, including #13–#16 and #18. Branch: `test/21-security-verification`. User-confirmed admission policy: restricted groups require owner/Administrator approval. User-confirmed environment: **localhost only**.

**Status: local checks and the fixes below are complete; final issue sign-off is pending.** This is a targeted application review, not a security certification or a claim that unimplemented/deployed features passed.

## Acceptance coverage

| #21 acceptance criterion | Current evidence/status |
|---|---|
| Unauthenticated access to protected features | PASS for implemented APIs: session/dashboard, groups/folders, materials/view/download/HEAD, quiz create/publish/start/submit/receipt, Administrator page/API, membership requests/review and logout. Valid login/static shells remain public by design. |
| Role restrictions and other groups' resources | PASS for implemented role/group checks, quiz attempt ownership, Administrator management, fresh write authorization, open joining and restricted admission/review. A pending request grants no membership or resource access. |
| Passwords and quiz keys absent from Student responses | PASS for actual populated published-quiz/start/submit/receipt responses and session/dashboard/group/material data. Salted PBKDF2 storage and safe registration-helper output are tested; the helper check does not pretend a full registration UI/API was exercised. The current account's CSRF token and its own selected answers are intentionally available to its UI. |
| Secure communication in deployed environment | **NOT VERIFIED: no deployed environment/HTTPS address exists or was supplied.** Localhost HTTP and the Secure-cookie configuration check are development evidence only, not deployed TLS proof. |
| Record findings and resolve failures | Four finding categories below reproduced and fixed locally. Full results/performance checks remain pending integration of #17/PR #39. Keep #21 open. |

## Findings reproduced and fixed

### SEC-01 — restricted group admission bypass

Before: any Student knowing an existing group ID could directly add membership through `/api/groups/{id}/join`; the data model did not distinguish open from restricted groups. This allowed a Student to turn a denied private-resource request into an allowed one without owner review.

Fix: `study_groups.join_policy` is `open` or `approval`. Restricted joins return 202/pending and create no membership. Only a current group owner with management authority or an Administrator can approve/decline. Decisions serialize with membership insertion and commit before confirmation. Repeated pending joins and repeated matching decisions do not duplicate membership. Reviewed requests are immutable; a later reapplication gets a new record, and replaying an old approval cannot restore revoked membership.

Migration: existing groups become approval-required because the previous schema had no explicit public/private distinction; existing members retain access. New groups default to approval and can explicitly choose Open joining at creation. Fixed demo memberships are read-only; normal-mode local accounts support the complete workflow. Group creation and upload/folder operations retain their existing role restrictions.

UI: Student dashboards accept the group ID supplied by an instructor and show the Student's own request history. Owner/Administrator dashboards show reviewable requests with Approve/Decline controls. Group cards include IDs and admission policy. Private group names are omitted from a nonmember Student's request history until membership exists.

### SEC-02 — backup source symlinks could copy outside data

Before: `copytree` dereferenced a symbolic link from storage before the backup manifest checked for links. An isolated reproduction copied an outside-file sentinel into the backup. Symlinked root/database/manifest components also passed prior validation.

Fix: validate source paths and contents; copy links as links so validation rejects them instead of reading their targets; reject symbolic-link backup components and non-regular storage objects. Verification uses temporary sentinel files, not real user secrets.

### SEC-03 — restored database could be readable by other local users

Before: an isolated restore into a 0755 parent left the database 0644 under a normal umask. That could expose academic records, password/session hashes and answer keys to other OS users.

Fix: backup/restore output parents must be owned private directories (0700 on POSIX). Backup databases/manifests/files and restored files use 0600, directories 0700. Shared restore destinations are refused before replacing existing data. Existing source files are not silently chmodded or deleted. Backup checksum and foreign-key validation remain active. Permissions were checked on macOS/POSIX; no Windows ACL verification is claimed.

### SEC-04 — stale authorization during pending writes

Before: group/folder/upload code could use an earlier role lookup even if an Administrator revoked that access before the final write. Regression checks reproduced a group creation returning 201 after such a revocation, and a stale folder-author context was accepted.

Fix: those HTTP mutations recheck the session and CSRF inside the write transaction before saving; upload scope/folder association is rechecked there too. Folder/admission helpers also reread current account role/active state. A role/status change and token revocation between the first lookup and write now denies the operation. Existing fresh-authority checks in quizzes/scoring/Administrator management are preserved.

## Executed checks

- **231 Python tests passed** on Python 3.14 and Python 3.12: 199 merged tests plus 17 security-verification and 15 membership-approval tests.
- **88 JavaScript tests passed**: 81 merged tests plus 7 membership-controller tests.
- Python compilation, membership/dashboard/attempt JavaScript syntax and diff checks passed. CI retains pinned Actions and Python 3.11/3.12; this local change has not been pushed, so no new remote CI result is claimed.
- A real isolated Chrome flow passed Student login → private material denied → pending restricted join still denied → owner login and approval → Student login and authorized read. Reviewer identity, one membership and immutable decision state were checked in SQLite.
- A second real Chrome flow passed Instructor create/publish → Student start → unanswered warning → confirmed submission → saved score → an altered repeated submission returning the original result. Grading data remains private while the new admission code is loaded.
- Other regressions cover direct nonmember reads, forged identity/score values, second-Student receipts, anonymous requests, invalid CSRF, inactive accounts, account/password response secrecy, backup links/permissions, stale/unauthorized review, concurrent opposing decisions, replayed old approvals, and additive legacy-group migration.

All active mutation/security tests used temporary databases, accounts and storage. No existing user's role, membership, password or files were changed for testing.

## Remaining sign-off items

1. **#17 / PR #39 is still unmerged and has conflicts.** The new Student result-history and Instructor-performance endpoints cannot be marked passed on current main. After integration, test real populated responses for own/other Student records, managed/foreign quiz groups, password/key omission, revoked roles and sessions. A missing route/404 is not a successful security test of an unimplemented feature.
2. **Deployed HTTPS**: when a deployment exists, check HTTPS reachability and certificate validity, HTTP redirect/rejection behavior, authenticated request transport and cookie flags through the actual proxy. `--secure-cookies` alone is not encryption. If the project is assessed exclusively as localhost development, obtain an explicit scope decision that the deployment criterion is Not Applicable; do not silently mark it passed.
3. Re-run the suite and relevant browser/API checks after #19/#20 or other late changes affect protected flows. #22 load/performance verification and external penetration/malware testing are separate from this targeted review.

A partial hardening PR should reference **Related to #21**, without an automatic closing keyword. Keep #21 **In progress** until the applicable remaining checks are recorded and accepted.
