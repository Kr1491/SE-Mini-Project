"""Results history integrates with #16 receipts and current authorization."""
import json
import unittest
import test_quiz_scoring as scoring
from study_platform.db import connect, initialize
from study_platform.quizzes import start_quiz_attempt


class ResultsSecurityTests(unittest.TestCase):
    setUp = scoring.QuizScoringTests.setUp
    tearDown = scoring.QuizScoringTests.tearDown
    request = scoring.QuizScoringTests.request
    sign_in = scoring.QuizScoringTests.sign_in
    submit = scoring.QuizScoringTests.submit

    def history(self):
        return self.request('GET', '/api/results/me')

    def test_guests_and_other_roles_cannot_read_student_history(self):
        self.cookie = ''
        for path in ['/api/results/me', '/api/groups/1/results']:
            self.assertEqual(self.request('GET', path)[0], 401)
        for uid in [1, 3]:
            self.sign_in(uid)
            self.assertEqual(self.history()[0], 403)

    def test_only_finalized_saved_grades_appear_and_retry_does_not_duplicate(self):
        self.assertEqual(self.history()[1]['results'], [])
        self.submit(); self.submit([])
        with connect(self.database) as db:
            start_quiz_attempt(db, {'id': 2, 'role': 'student'}, self.quiz_id)
        rows = self.history()[1]['results']
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['score'], rows[0]['total_questions'], rows[0]['percentage']), (2, 2, 100))
        self.assertEqual(rows[0]['id'], self.attempt)
        self.assertEqual(set(rows[0]), {'id','quiz_id','quiz_title','score','total_questions','percentage','submitted_at'})

    def test_supplied_student_id_cannot_reveal_another_students_history(self):
        self.submit(); self.sign_in(4)
        status, data, _ = self.request('GET', '/api/results/me?student_id=2&user_id=2')
        self.assertEqual(status, 200); self.assertEqual(data['results'], [])
        self.assertEqual(self.request('GET', '/api/groups/1/results')[0], 403)

    def test_staff_membership_does_not_grant_management_of_another_group(self):
        self.submit(); self.sign_in(1)
        with connect(self.database) as db:
            db.execute('INSERT INTO memberships VALUES(3,1)')
        self.assertEqual(self.request('GET', '/api/groups/3/results')[0], 403)
        status, data, _ = self.request('GET', '/api/groups/1/results')
        self.assertEqual(status, 200); self.assertEqual(data['results'][0]['student_name'], 'Demo Student')
        serialized = json.dumps(data)
        for private in ['password_hash','token_hash','grading_snapshot','correct_option_id','is_correct']:
            self.assertNotIn(private, serialized)
        self.sign_in(3)
        self.assertEqual(self.request('GET', '/api/groups/1/results')[0], 200)

    def test_revoked_group_membership_hides_history(self):
        self.submit()
        with connect(self.database) as db:
            db.execute('DELETE FROM memberships WHERE user_id=2 AND group_id=1')
        self.assertEqual(self.history()[1]['results'], [])

    def test_role_and_suspension_changes_take_effect_with_existing_cookie(self):
        self.submit()
        with connect(self.database) as db:
            db.execute("UPDATE users SET role='instructor' WHERE id=2")
        self.assertEqual(self.history()[0], 403)
        with connect(self.database) as db:
            db.execute('UPDATE users SET is_active=0 WHERE id=2')
        self.assertEqual(self.history()[0], 401)

    def test_completed_legacy_attempt_has_unknown_grade_and_reinitialization_preserves_new_grade(self):
        self.submit()
        with connect(self.database) as db:
            db.execute("INSERT INTO quiz_attempts(quiz_id,student_id,submitted_at) VALUES(?,2,'2026-10-01T10:00:00Z')", (self.quiz_id,))
        initialize(self.database)
        rows = self.history()[1]['results']
        self.assertEqual(len(rows), 2)
        graded = next(row for row in rows if row['id'] == self.attempt)
        legacy = next(row for row in rows if row['id'] != self.attempt)
        self.assertEqual(graded['score'], 2)
        self.assertEqual((legacy['score'], legacy['total_questions'], legacy['percentage']), (None, None, None))
