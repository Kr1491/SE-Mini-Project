# Issue #16 — submission and scoring contract

This change is based on main 339d4c4, including the real #13 creation, #14 publication and #15 attempt implementation. It does not apply the earlier sample-quiz draft or the paused #21 security changes.

## Scoring policy

The current merged quiz schema supports single-answer MCQs without question weights. Each question is worth **one point**. A selected correct option earns 1; an incorrect option, omitted question or explicit null option earns 0. All questions count toward max_score. No negative marks, partial credit, weighted scores or short-answer grading are introduced.

At `POST /api/quizzes/{id}/attempts`, the server freezes the quiz/group IDs, title, question text, option IDs/text and private correct option for that version. The existing start response is unchanged and only receives the public question/option projection. Later changes to an answer flag do not change an existing attempt's grading key; added questions do not change its denominator. If required question/option records are removed or moved, submission fails safely instead of guessing a grade. The current application has no question-edit/delete API; future editing/deletion work must preserve historical answers and their foreign-key relationships.

## Tables and migration

- `quiz_attempts.grading_snapshot`: nullable private JSON. New attempts always receive version 1; NULL identifies pre-scoring legacy attempts. Never serialize this column in Student responses.
- `quiz_attempt_answers`: unchanged table and `(attempt_id, question_id)` primary key. Only actual selections are stored; omitted/null selections have no row. Validation ensures the option belongs to the frozen question and the attempt's quiz.
- `quiz_attempt_results`: one row per `attempt_id` (primary/foreign key), containing integer `score`, `max_score`, `answered_count` and UTC `submitted_at`. `max_score` equals the frozen question count, and `unanswered_count = max_score - answered_count`.

Identity comes from the authenticated account and stored attempt, not client fields. Client-supplied scores, answer-key flags, role, quiz_id or student_id do not determine grading. Finalization uses `BEGIN IMMEDIATE` across fresh account/group checks, validated answers, result insertion and the attempt timestamp. Callers use `with connect(...)` and let failures roll back, then commit before sending HTTP success.

One result is saved per attempt, not per quiz/student pair. The #15 API can still create a legitimate new attempt when a Student starts again. Repeated requests for the same finalized attempt return the saved result, selected answers and original timestamp. New answer payloads never overwrite a finalized attempt.

Initialization adds the snapshot column and result table without replacing existing rows. Legacy active attempts cannot be reliably reconstructed as-of-start, so they require a fresh start. Legacy completed attempts return a receipt with `result: null` and preserved answers; show **Score unavailable/Not graded**, not zero. No historical grades are backfilled.

## HTTP contract

`POST /api/quiz-attempts/{attempt_id}/submit` keeps the existing #15 route and request:

```json
{"answers":[{"question_id":12,"option_id":48}]}
```

An empty list submits all questions unanswered. A null option_id also means unanswered. IDs must be positive JSON integers within SQLite's signed range; duplicates, foreign options/questions and malformed values return 400 without saving partial answers. Authentication and the current session CSRF header are required.

Success/retry returns HTTP 200:

```json
{
  "attempt_id": 7,
  "quiz_id": 3,
  "student_id": 2,
  "submitted": true,
  "already_submitted": false,
  "result": {
    "score": 1,
    "max_score": 2,
    "answered_count": 1,
    "unanswered_count": 1,
    "submitted_at": "2026-11-02T08:00:00.000Z"
  },
  "answers": [{"question_id":12,"option_id":48}],
  "message": "Quiz submitted successfully. Your answers and score have been saved."
}
```

A retry sets already_submitted to true and returns the same stored result. The selected answers are the current Student's own submissions, not the grading key. `GET /api/quiz-attempts/{id}/result` retrieves the same private receipt after submission. Both endpoints require an active Student account, ownership and current group scope. Non-Student roles are denied; another Student's attempt is treated as not found. New submissions additionally require a currently published quiz. An already-submitted receipt remains available if the quiz later becomes a draft, provided account/ownership/group authorization still passes.

401 = missing/expired/inactive session; 403 = role/group/CSRF denial; 404 = missing/other Student attempt; 409 = not submitted yet, pre-scoring active attempt, unavailable/changed quiz data or inconsistent saved state. Invalid oversized path IDs return 400 instead of a database overflow.

## Handoff to Anushree for #17

Join `quiz_attempt_results.attempt_id` to `quiz_attempts.id`, then use the attempt's student_id/quiz_id and the quiz's group/creator relationships. Use an appropriate LEFT JOIN if historical ungraded submissions must be shown; a missing result is not a score of zero. Retakes are separate attempts, so decide explicitly whether a report shows all, latest or best attempts.

Student history must authorize the current Student's own records and the agreed resource scope. Instructor performance routes must separately enforce the Instructor/Administrator policy and management of the quiz's group; the Student receipt endpoint does not impersonate another Student for staff. Question-by-question review should use the private snapshot through a separately authorized server projection, never expose its grading key during an active Student attempt.

The current #16 UI shows immediate submission confirmation only. Results history, performance analytics and their dashboard actions remain #17.
