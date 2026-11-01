# PR #35 — quiz creation integration checks

Reviewed 1 November 2026. Original PR head: 472a184. Latest main incorporated: dbfeff3 (backup/recovery #34).

## Findings resolved before merge

- The database conflict overlapped `QUIZ_SCHEMA` with `_migrate_upload_idempotency`. Both are preserved, and initialization creates quiz tables while retaining upload retries, material/folder migrations, account versions and audit data.
- Nine frontend CI tests failed after the new quiz selector setup assumed a native select-options collection unavailable in the test DOM. Placeholder setup now uses the created option directly; the existing dashboard tests pass with the quiz feature.
- Quiz authoring drafts/answer selections are cleared when accounts change, logout begins or a refresh loses authorization. Old pending save responses cannot update a different account's interface. A second submission while saving is ignored, and the editor is disabled until the request finishes.
- Quiz text is bounded and rejects invalid UTF-8/surrogate or NUL content with 400 rather than a server error. Titles allow 160 characters, questions 1000 and options 500; a quiz supports 1–100 questions and 2–20 options per question, within the existing HTTP request-size limit.
- Author role/active status is reread under the write transaction so stale authority cannot create a quiz after revocation. Invalid or failed question/option inserts roll back the whole quiz.

## Validation

- 167 Python tests passed locally on Python 3.12 and 3.14.
- 69 JavaScript tests passed; Python compilation, dashboard JavaScript syntax and diff checks passed.
- A real isolated Chrome flow passed Instructor sign-in → Create quizzes → create a two-question/four-option quiz → successful confirmation → Student sign-in. The database contained exactly one quiz, two questions and eight options, with the chosen two correct answers saved correctly.
- Student quiz responses omitted `is_correct`; Student authoring, private-group reads and unauthenticated reads returned 403/403/401 respectively.
- A backup/restore test recovered quiz questions and their correct-answer flags alongside the upload-idempotency schema and sample stored file.
- GitHub Python 3.11/3.12 CI is required to pass on the updated PR before merging. Post-merge checks are run separately; no full-project security certification is claimed.

## Scope

This PR completes quiz creation and MCQ question/answer entry (#13). Publishing/listing rules (#14), starting and answering attempts (#15), submission/scoring (#16), and result/performance views (#17) remain separate work. The current sanitized group-quiz retrieval does not yet implement publication-state filtering; #14 must add that before treating the quiz flow as a finished student assessment feature.

All verification used temporary databases and storage. No existing local user data was edited for these checks.
