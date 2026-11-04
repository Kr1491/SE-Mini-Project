# Issue #16 — validation

Base: merged main 339d4c4. Branch: feat/16-quiz-submission. Earlier #16 sample work and #21 changes remain saved separately and are not applied.

- **199 Python tests pass** on Python 3.12 and 3.14 (175 existing tests plus 24 scoring tests).
- **81 JavaScript tests pass** (69 existing tests plus 12 attempt-controller tests).
- Python compileall, quiz-attempt.js/dashboard.js syntax and git diff --check pass. CI adds a syntax check for the new controller and retains pinned Actions plus Python 3.11/3.12.
- A real isolated Chrome flow exercised Instructor login → create two-question quiz → publish → Student login → Available quizzes → start → choose one correct answer and leave one unanswered → warning → explicit confirmation → saved **1/2** score. Before confirmation the result endpoint returned 409. A subsequent altered payload with a forged score returned the original score/timestamp. Database checks found exactly one result and one selected-answer row.

## Acceptance evidence

| Criterion | Evidence |
|---|---|
| Answers saved against correct Student/quiz | Session and stored attempt determine identity. Tests forge body IDs/roles/scores and try a second Student's attempt. |
| Accurate server scoring | Correct/wrong/missing/all-empty/null selections; frozen key after answer-flag changes; stable denominator after added questions. No client score is trusted. |
| Consistent unanswered handling | Missing/null options earn zero, remain in max_score, and appear in receipt counts; UI warns before confirmation. |
| No duplicate results | Repeat and concurrent requests return one original result/answer set; altered replay cannot overwrite it. |
| Successful confirmation | Commit-before-response test, private result GET, saved-score UI and real browser flow. |

Additional coverage includes role/account/membership revocation, CSRF and anonymous denial, question/option validation and bounded IDs, unpublished quizzes, corrupted/deleted snapshot data, transactional rollback with retry, additive legacy migration, preservation of old ungraded submissions, and backup/restore of grading data. UI tests cover duplicate clicks, frozen network-retry payloads, stale responses after close/account change, authorization-loss clearing, errors, literal text, true zero scores and legacy unavailable scores.

Remote CI has not run for this local change yet. These checks are not the final #21 security review or #22 load/performance verification.

## Manual checks

1. Restart the backend with this branch and the local normal-mode test database. Sign in as Instructor, create a quiz in a group the Student belongs to, and publish it.
2. Sign out; sign in as Student and open Available quizzes. Start the quiz and select/change options.
3. Submit with one unanswered question. Confirm that the warning appears before any score is saved. Keep editing should restore editable selections.
4. Confirm submission. Check the server score, answered/unanswered counts and locked inputs. Back to quizzes should clear the old answer/score screen.
5. Repeat the same submission request or simulate a lost response and retry. Only the original result should remain. A new Start creates a distinct attempt by the existing #15 policy.
6. Another Student, nonmember, Instructor or Administrator cannot submit/read the Student receipt through this personal endpoint. Expired sessions or changed access should clear the attempt UI on denial.
7. Existing in-progress attempts from before scoring require a fresh start. Earlier completed answers remain stored but have no invented score. Results history/performance is separate #17 work.
