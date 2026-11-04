Students now receive a saved server-calculated score after confirming a quiz submission. This extends the merged #13/#14/#15 quiz creation, publishing and attempt flow. Each MCQ is worth one point; incorrect or unanswered questions receive zero, and every question remains in the denominator. Selected answers retain their existing student/quiz association through the attempt record.

A private question/option/key snapshot is frozen when an attempt starts. Finalization checks current Student role, active state, ownership, group membership and publication under a write transaction; validates selections against the snapshot; and saves answers, result and submission timestamp atomically before returning confirmation. One result row per attempt and serialized writes make retries—including concurrent or altered retries—return the original receipt without overwriting answers or adding results. The receipt never includes answer keys.

The UI warns about unanswered questions, asks for explicit confirmation, locks the submitted answers and shows the saved score. An uncertain network response retries the same confirmed payload. Closing, account switching and authorization loss clear the attempt state and ignore stale responses.

Compatibility: existing answers/attempts are preserved. Older in-progress attempts without a grading snapshot require a fresh attempt; old completed attempts remain ungraded rather than receiving invented historical scores. `docs/issue-16-integration.md` documents the result table and receipt contract for #17. Results history and instructor performance views remain #17 work; paused #21 changes are not included.

Validation: 199 Python tests pass on 3.12 and 3.14; 81 JavaScript tests pass. Compilation, JavaScript syntax and diff checks pass. An isolated Chrome flow passed Instructor creation/publication → Student start → unanswered warning → confirmation → persisted 1/2 score. A repeated submission with altered answers and a forged score returned the same original result; database counts confirmed one result and one selected-answer row. Remote CI follows the user's push.

Closes #16
