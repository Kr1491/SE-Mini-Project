# Issue #21 — local security verification and remediation

Review completed **4 November 2026** against merged main **53cc60a**, including #13–#18 and results/performance PR #39. Branch: `test/21-security-verification`. User-confirmed admission policy: restricted groups require owner/Administrator approval. User-confirmed environment: **localhost only**.

**Status: complete for the user-confirmed localhost scope.** This is a targeted application review, not a security certification or a claim that unimplemented/deployed features passed.

## Acceptance coverage

| #21 acceptance criterion | Current evidence/status |
|---|---|
| Unauthenticated access to protected features | PASS for implemented APIs: session/dashboard, groups/folders, materials/view/download/HEAD, quiz create/publish/start/submit/receipt, own results and managed-group performance, Administrator page/API, membership requests/review and logout. Valid login/static shells remain public by design. |
| Role restrictions and other groups' resources | PASS for implemented role/group checks, quiz attempt ownership, Administrator management, fresh write authorization, open joining and restricted admission/review. A pending request grants no membership or resource access. |
| Passwords and quiz keys absent from Student responses | PASS for actual populated published-quiz/start/submit/receipt responses and session/dashboard/group/material/result-history/performance data. Salted PBKDF2 storage and safe registration-helper output are tested; the helper check does not pretend a full registration UI/API was exercised. The current account's CSRF token and its own selected answers are intentionally available to its UI. |
| Secure communication in deployed environment | **NOT APPLICABLE to the user-confirmed localhost-only environment; deployed HTTPS is NOT VERIFIED.** No deployed HTTPS address exists or was supplied. Localhost HTTP and Secure-cookie configuration are development evidence, not TLS proof. |
| Record findings and resolve failures | Four finding categories below reproduced and fixed. PR #39 was reconciled with #16, passed CI on Python 3.11/3.12 and merged; populated results/performance checks now pass. |

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

- **242 Python tests passed** on Python 3.14 and Python 3.12: 210 merged tests plus 17 security-verification and 15 membership-approval tests.
- **95 JavaScript tests passed**: 88 merged tests plus 7 membership-controller tests.
- Python compilation, membership/dashboard/attempt JavaScript syntax and diff checks passed. CI retains pinned Actions and Python 3.11/3.12; the initial #21 commit passed remote CI on both versions. Final integration CI runs on the updated PR head before merge.
- A real isolated Chrome flow passed Student login → private material denied → pending restricted join still denied → owner login and approval → Student login and authorized read. Reviewer identity, one membership and immutable decision state were checked in SQLite.
- A second real Chrome flow passed Instructor create/publish → Student start → unanswered warning → confirmed submission → saved score → an altered repeated submission returning the original result. Grading data remains private while the new admission code is loaded.
- Other regressions cover direct nonmember reads, forged identity/score values, second-Student receipts, anonymous requests, invalid CSRF, inactive accounts, account/password response secrecy, backup links/permissions, stale/unauthorized review, concurrent opposing decisions, replayed old approvals, and additive legacy-group migration.

- A third real Chrome flow passed Student login → own results (1/2, 50%) → logout → Instructor login → managed-group performance. Student staff-results access and Instructor foreign-group results both returned 403. Actual result responses omit grading snapshots, answer keys and credential/session hashes; responses use no-store.
- Results regressions additionally cover forged Student IDs, another Student's empty own history, membership revocation, changed role/inactive account, unsubmitted attempts, repeated submission without duplicated history and legacy submissions with unknown grades. The results UI clears private content on logout/denial and ignores stale account/group completions.

All active mutation/security tests used temporary databases, accounts and storage. No existing user's role, membership, password or files were changed for testing.

## Scope decision and future changes

The user identified this project as localhost-only and requested completion in that environment. All applicable local checks above are complete. The deployed-communication criterion is recorded as **Not Applicable to this environment**, not passed. No HTTPS deployment or security certification is claimed. When deployment is introduced, verify HTTPS reachability, certificate validity, HTTP redirect/rejection, authenticated request transport and cookie flags through the actual proxy; `--secure-cookies` alone does not provide encryption.

Re-run the security suite and relevant browser/API checks when #19/#20 or later changes affect protected flows. #22 load/performance verification and external penetration/malware testing remain separate from this targeted review.

PR #40 can close #21 for this documented local scope after the final integration checks pass. Move the board item to Done only after that PR is merged.
