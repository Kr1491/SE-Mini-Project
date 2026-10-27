# Issue #6 validation — 27 October 2026

## Current integration results

Latest main includes merged #7 folders and #12 materials. All five conflicting files in PR #25 have been resolved by combining those features with the dashboard routes, tests, CI and documentation.

- Python 3.12 and 3.14: **92 tests pass** on each interpreter. This includes the 75 merged authorization/folder/material tests plus 17 dashboard tests.
- Node.js: **41 tests pass**: 30 merged access/folder/material checks plus 11 dashboard checks.
- Python compilation and JavaScript syntax checks for app.js, dashboard.js, folders.js and materials.js pass.
- A real loopback server using temporary private fixtures passed checks for public assets, dashboard root, preserved `/access` folders, all three role pages/APIs, rejected cross-role access, available folder/material actions, folder creation/listing, exact PDF downloads, HEAD and byte ranges, and private/nonmember denial.

Dashboard-specific backend coverage includes anonymous denial; distinct role summaries/navigation; group scoping; cross-role API/page rejection; ignored client roles/IDs; empty groups; membership revocation; database-backed active counts; active peers limited to visible groups; instructor membership versus management; literal profile/group text; omitted session/password secrets; unavailable tools without links; folder/material capability and permission gates; normal-mode sessions; and preserved asset routes.

Frontend coverage includes startup gating; replacement of role/profile/navigation; empty states; literal names; stale refresh protection; clearing private data on failure; hidden sample selection in normal mode; direct-role denial; contrast; and exact allowlisted links to the merged folder and material workspaces. Lookalike material destinations are rejected.

Python 3.11 remains covered by the configured CI matrix; no local 3.11 result is claimed. Updated remote CI and interactive browser checks remain pending the user's push/run.

## Manual verification before Done

Run `mkdir -p var`, `chmod 700 var`, and `python3 server.py --demo --port 8003`.

- Select Student, Instructor and Administrator at `/`. Check the correct title, tools, counts and groups.
- Open Group folders: `/access#folders-panel` must retain its picker, creation form and role restrictions.
- Open Study materials: `/materials` must retain previews/downloads and permitted group scoping for each account.
- A student without memberships sees no private groups/files. A direct page for another role is denied.
- Account switching/refresh must not retain the previous account's content. Future tools remain unavailable.
- Check narrow widths, keyboard navigation and the browser console. Verify real login integration after Jiya's module merges.
- Complete review, passing CI, merge and verification before marking #6 Done.
