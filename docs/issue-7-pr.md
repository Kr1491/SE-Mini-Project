Adds folder listing and creation within authorized study groups. Instructors can create folders in groups they own, administrators can manage folders in all groups, and student/group members have read-only access. The UI uses the existing authenticated session and server-provided permissions.

Closes #7

Folder names are validated, normalized to Unicode NFC and compared with Unicode casefold for group-scoped duplicates. SQLite enforces uniqueness and group/user foreign keys. Successful creation is committed before returning 201; folders persist across refresh/reinitialization. The UI ignores stale group/account responses, prevents repeated submissions, and displays names as literal text.

Validation:
- 51 Python tests pass locally on Python 3.12 and 3.14.
- 15 Node frontend tests pass, including existing role-access regressions.
- Python compilation and both JavaScript syntax checks pass.
- CI retains the Python 3.11/3.12 matrix and pinned Actions; remote results are pending the push.
- Live browser verification is pending because this execution environment blocks TCP listeners.

Depends on merged issue #5. Dashboards (#6), material viewing/downloading (#12), authentication, group creation/membership and uploads remain separate work. Demo users/groups are fixtures; this PR does not claim that the full Sprint 1 journey is integrated.
