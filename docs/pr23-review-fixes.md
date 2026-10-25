# PR #23 — review findings and responses

All 10 findings supplied in the chat are valid and addressed in this prepared change. No GitHub replies, thread resolutions, commits, or pushes were performed by the assistant. The replies below can be used after the change is applied and pushed, and the CI results are checked.

| Finding | Root cause | Change and verification | Suggested reply after pushing |
|---|---|---|---|
| Demo fixture-ID collisions | INSERT OR IGNORE reused arbitrary existing IDs without proving fixture identity. | Require an empty database on first seed; record a fixture marker; revalidate exact fixture users/groups/memberships at startup and before selection. Use a separate default demo path. Tests verify conflicts fail closed and original records are preserved. | Valid. Demo now requires a dedicated empty or verified fixture database, and the selector rechecks fixture identity before creating a session. |
| Probe-response ordering | Independent async responses unconditionally updated the same result. | A request sequence and account revision ignore stale successes/errors; delayed-response tests exercise both orderings and account changes. | Valid. Only the latest probe for the current account may update the displayed result. |
| Initial-session/account-selection race | Account selection became available before initial session detection settled. | Keep the selector hidden and event handler guarded until initialization settles. Test delays the anonymous session response and then selects a new account. | Valid. Selection is enabled only after initial session detection completes. |
| Cookie sent before session commit | Response was sent inside a transaction that committed only on context exit. | Explicitly commit token creation/revocation before sending Set-Cookie. Test inspects the database from a separate connection before response delivery. | Valid. The new session and revocation are committed before the cookie response is sent. |
| Secondary-text contrast | Foreground colors produced approximately 4.15:1, 4.18:1 and 3.92:1 on their backgrounds. | Darken secondary text to #4d6258; measure 6.14:1 on page background and 6.56:1 on white panels. Test actual stylesheet colors. | Valid. The three secondary-text styles now exceed 4.5:1 contrast on their backgrounds. |
| Nullable session primary key | SQLite's ordinary TEXT PRIMARY KEY did not imply NOT NULL. | Add explicit NOT NULL and migrate existing tables; preserve classified valid tokens, omit malformed null rows, and invalidate tokens without mode provenance. | Valid. token_hash now explicitly rejects NULL, including after migration of an existing database. |
| Database file/directory permissions | SQLite file creation inherited the process umask. | Create files as 0600 in a dedicated 0700 parent; tighten existing owned files, reject shared parents and symlink database paths. POSIX tests cover permissive umask and existing files/directories. | Valid. Database creation now enforces owner-only POSIX storage and refuses an unsafe containing directory. |
| Mutable Action tags | Workflow used movable major tags. | Pin checkout and setup-python to full release commit SHAs, with version comments and provenance links below. | Valid. Both Actions are pinned to full verified release commit SHAs. |
| IPv6 loopback handling | ::1 was allowed while the server class supported only IPv4. | Explicitly reject IPv6 before initialization/binding; retain supported IPv4 loopback hosts. Tests confirm no IPv4 server construction is attempted for ::1. | Valid. IPv6 is explicitly unsupported and rejected with an actionable error; 127.0.0.1 remains supported. |
| Untested Python minimum | CI exercised 3.12 but README declared 3.11+. | Matrix includes 3.11 and 3.12 with fail-fast disabled. Local tests pass on 3.12 and 3.14; 3.11 awaits CI. | Valid. CI now tests Python 3.11 and 3.12; please check both jobs after this push. |

## Additional defects reproduced independently

- Demo-generated sessions were accepted after switching to normal mode. Sessions now carry mode provenance, and normal mode rejects demo tokens. Unclassified legacy sessions require a fresh login.
- Out-of-range group IDs caused SQLite overflow/server errors. Requests now validate the signed 64-bit ID range and return 400.
- Non-ASCII CSRF headers caused compare_digest to raise a TypeError. Comparison now uses UTF-8 bytes and returns 403 for invalid tokens.

## Validation and limits

35 Python tests pass on local Python 3.12 and 3.14, plus five Node tests. Compile/syntax checks pass. CI's Python 3.11 result, remote workflow execution and live-browser verification remain pending. Only issue #5 is addressed; no #6/#7/#12 implementation is added.

## Source verification

- [actions/checkout v7.0.0 release](https://github.com/actions/checkout/releases/tag/v7.0.0): commit `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0`.
- [actions/setup-python v7.0.0 release](https://github.com/actions/setup-python/releases/tag/v7.0.0): commit `5fda3b95a4ea91299a34e894583c3862153e4b97`.
- [WCAG 2.2 contrast requirement](https://www.w3.org/TR/WCAG22/#contrast-minimum): 4.5:1 for normal text.

## Applying and pushing

If the actual workspace is still restricted because the folder was renamed, run `git apply --check` on the supplied review patch from the actual repository, then `git apply` if the check succeeds. Git refuses a conflicting patch. The original code is already preserved in commit f1f11f4, and the patch only updates the review files; applying it does not stage, commit, push, or post to GitHub.

Continue on `feat/5-role-access`; committing and pushing this branch updates existing PR #23. Return #5 to In progress while fixing it, then In review after pushing and requesting re-review. Resolve review conversations only after the relevant change and validation are visible, and keep the PR unmerged until the remaining review/checks are complete.
