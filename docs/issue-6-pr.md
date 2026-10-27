Build role-specific Student, Instructor and Administrator dashboards with database-backed summaries, scoped study groups, role-appropriate navigation and feature availability. The landing page opens the current account's dashboard; direct role pages and APIs require the matching authenticated role.

This branch incorporates latest main, including merged folder (#7) and material (#12) features. Folder tools open `/access#folders-panel`; all three roles can open `/materials` when the server capability and material-read permission are present. Each destination retains session, role and group authorization. Existing access checks and folders remain at `/access`.

Profile/group names render as literal text, failed refreshes clear private data, and account switching ignores stale responses. Unimplemented quiz and user-management tools stay Coming soon without dead links or invented counts. No real registration/login, upload, quiz, or account-management implementation is added.

Validation: 92 Python tests pass on 3.12 and 3.14; 41 frontend tests pass. Compilation and all four JavaScript syntax checks pass. Live loopback HTTP checks pass for each role dashboard, cross-role denial, folder creation/listing, material downloads, HEAD/ranges, and private/nonmember denial. CI retains pinned actions and Python 3.11/3.12 coverage; updated remote CI and interactive browser verification remain pending.

Closes #6
