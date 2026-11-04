"""Issue #16: authoritative MCQ grades, privacy, atomicity and repeat receipts."""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import server
import test_access as access
from study_platform.db import connect,initialize
from study_platform.quizzes import create_quiz,publish_quiz,start_quiz_attempt
from study_platform.quiz_scoring import submit_attempt
from study_platform.security import APIError,COOKIE_NAME,create_session


class QuizScoringTests(unittest.TestCase):
    request=access.AccessTests.request
    tearDown=access.AccessTests.tearDown

    def setUp(self):
        access.AccessTests.setUp(self)
        self.server.demo=False
        quiz={'title':'Scoring quiz','questions':[
            {'question':'First question','options':[{'text':'Correct A','is_correct':True},{'text':'Wrong B','is_correct':False}]},
            {'question':'Second question','options':[{'text':'Wrong C','is_correct':False},{'text':'Correct D','is_correct':True}]}]}
        with connect(self.database) as db:
            teacher={'id':1,'role':'instructor'}
            self.quiz_id=create_quiz(db,teacher,1,quiz)['id']
            publish_quiz(db,teacher,self.quiz_id)
            self.started=start_quiz_attempt(db,{'id':2,'role':'student'},self.quiz_id)
            self.correct=[{'question_id':row['qid'],'option_id':row['oid']} for row in db.execute('''SELECT q.id AS qid,o.id AS oid FROM quiz_questions q JOIN quiz_options o ON o.question_id=q.id WHERE q.quiz_id=? AND o.is_correct=1 ORDER BY q.position''',(self.quiz_id,))]
        self.attempt=self.started['attempt_id'];self.sign_in(2)

    def sign_in(self,uid):
        with connect(self.database) as db:token,self.csrf=create_session(db,uid)
        self.cookie=f'{COOKIE_NAME}={token}'

    def submit(self,answers=None,attempt=None,**options):
        return self.request('POST',f'/api/quiz-attempts/{attempt or self.attempt}/submit',{'answers':self.correct if answers is None else answers},**options)

    def result(self):return self.request('GET',f'/api/quiz-attempts/{self.attempt}/result')

    def test_correct_answers_are_saved_with_server_score_and_student_quiz(self):
        status,data,_=self.submit()
        self.assertEqual(status,200)
        self.assertEqual((data['student_id'],data['quiz_id'],data['attempt_id']),(2,self.quiz_id,self.attempt))
        self.assertEqual((data['result']['score'],data['result']['max_score']),(2,2))
        self.assertFalse(data['already_submitted'])
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempt_answers WHERE attempt_id=?',(self.attempt,)).fetchone()[0],2)
            self.assertIsNotNone(db.execute('SELECT submitted_at FROM quiz_attempts WHERE id=?',(self.attempt,)).fetchone()[0])
            self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempt_results').fetchone()[0],1)

    def test_wrong_and_missing_answers_score_zero_with_full_denominator(self):
        wrong=self.started['quiz']['questions'][0]['options'][1]['id']
        status,data,_=self.submit([{'question_id':self.correct[0]['question_id'],'option_id':wrong}])
        self.assertEqual(status,200)
        self.assertEqual((data['result']['score'],data['result']['max_score'],data['result']['answered_count'],data['result']['unanswered_count']),(0,2,1,1))

    def test_all_unanswered_and_explicit_null_are_consistent(self):
        status,data,_=self.submit([{'question_id':self.correct[0]['question_id'],'option_id':None}])
        self.assertEqual(status,200);self.assertEqual(data['result']['score'],0);self.assertEqual(data['result']['unanswered_count'],2)
        with connect(self.database) as db:
            another=start_quiz_attempt(db,{'id':2,'role':'student'},self.quiz_id)['attempt_id']
        status,data,_=self.submit([],attempt=another)
        self.assertEqual(status,200);self.assertEqual(data['result']['score'],0);self.assertEqual(data['result']['unanswered_count'],2)

    def test_forged_scores_roles_and_identity_do_not_affect_grading(self):
        status,data,_=self.request('POST',f'/api/quiz-attempts/{self.attempt}/submit',{'answers':[],'score':100,'student_id':3,'quiz_id':999,'role':'administrator','correct_answers':self.correct})
        self.assertEqual(status,200);self.assertEqual(data['result']['score'],0)
        self.assertEqual((data['student_id'],data['quiz_id']),(2,self.quiz_id))

    def test_repeated_request_returns_original_receipt_without_new_answers(self):
        first=self.submit()[1]
        second=self.submit([])[1]
        self.assertTrue(second['already_submitted']);self.assertEqual(first['result'],second['result']);self.assertEqual(first['answers'],second['answers'])
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempt_results').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempt_answers').fetchone()[0],2)

    def test_concurrent_retries_have_one_result_and_one_answer_set(self):
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:self.submit(),range(2)))
        self.assertEqual([item[0] for item in responses],[200,200])
        self.assertEqual(sorted(item[1]['already_submitted'] for item in responses),[False,True])
        self.assertEqual(responses[0][1]['result'],responses[1][1]['result'])
        with connect(self.database) as db:self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempt_results').fetchone()[0],1)

    def test_invalid_answer_options_and_duplicate_question_ids_are_rejected_atomically(self):
        qid=self.correct[0]['question_id'];other_option=self.correct[1]['option_id']
        for answers in [[{'question_id':qid,'option_id':other_option}], [self.correct[0],self.correct[0]],
                        [{'question_id':999,'option_id':1}],[{'question_id':True,'option_id':1}],
                        [{'question_id':qid,'option_id':True}],[{'question_id':qid,'option_id':'1'}],
                        [{'question_id':qid,'option_id':10**80}],['bad']]:
            self.assertEqual(self.submit(answers)[0],400,answers)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempt_answers').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempt_results').fetchone()[0],0)

    def test_missing_answers_object_and_oversized_attempt_ids_are_rejected(self):
        for data in [{},{'answers':{}},{'answers':None}]:
            self.assertEqual(self.request('POST',f'/api/quiz-attempts/{self.attempt}/submit',data)[0],400)
        for path in ['/api/quiz-attempts/'+'9'*100+'/submit','/api/quizzes/'+'9'*100+'/attempts','/api/quizzes/'+'9'*100+'/publish']:
            self.assertEqual(self.request('POST',path,{'answers':[]})[0],400)

    def test_other_student_cannot_submit_or_view_this_attempt(self):
        with connect(self.database) as db:db.execute('INSERT INTO memberships VALUES(1,4)')
        self.sign_in(4)
        self.assertEqual(self.submit()[0],404);self.assertEqual(self.result()[0],404)

    def test_instructor_admin_anonymous_and_bad_csrf_cannot_submit(self):
        self.assertEqual(self.submit(csrf=False)[0],403)
        for uid in [1,3]:
            self.sign_in(uid);self.assertEqual(self.submit()[0],403);self.assertEqual(self.result()[0],403)
        self.cookie='';self.assertEqual(self.submit()[0],401)

    def test_membership_role_and_account_revocation_block_submission(self):
        with connect(self.database) as db:db.execute('DELETE FROM memberships WHERE group_id=1 AND user_id=2')
        self.assertEqual(self.submit()[0],403)
        with connect(self.database) as db:
            db.execute('INSERT INTO memberships VALUES(1,2)');db.execute("UPDATE users SET role='instructor' WHERE id=2")
        self.assertEqual(self.submit()[0],403)
        with connect(self.database) as db:db.execute("UPDATE users SET role='student',is_active=0 WHERE id=2")
        self.assertEqual(self.submit()[0],401)

    def test_changed_answer_flags_do_not_regrade_an_existing_attempt(self):
        with connect(self.database) as db:
            db.execute('UPDATE quiz_options SET is_correct=1-is_correct')
        self.assertEqual(self.submit()[1]['result']['score'],2)

    def test_added_questions_do_not_change_existing_attempt_denominator(self):
        with connect(self.database) as db:
            qid=db.execute("INSERT INTO quiz_questions(quiz_id,question_text,position) VALUES(?,'New question',2)",(self.quiz_id,)).lastrowid
            db.executemany('INSERT INTO quiz_options(question_id,option_text,is_correct) VALUES(?,?,?)',[(qid,'A',1),(qid,'B',0)])
        data=self.submit()[1];self.assertEqual((data['result']['score'],data['result']['max_score']),(2,2))

    def test_corrupt_snapshot_and_deleted_structure_fail_without_writes(self):
        with connect(self.database) as db:
            original=db.execute('SELECT grading_snapshot FROM quiz_attempts WHERE id=?',(self.attempt,)).fetchone()[0]
            db.execute("UPDATE quiz_attempts SET grading_snapshot='not JSON' WHERE id=?",(self.attempt,))
        self.assertEqual(self.submit()[0],409)
        with connect(self.database) as db:
            db.execute('UPDATE quiz_attempts SET grading_snapshot=? WHERE id=?',(original,self.attempt))
            db.execute('DELETE FROM quiz_options WHERE id=?',(self.correct[0]['option_id'],))
        self.assertEqual(self.submit()[0],409)
        with connect(self.database) as db:self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempt_results').fetchone()[0],0)

    def test_unpublished_quiz_cannot_finalize_a_new_submission(self):
        with connect(self.database) as db:db.execute("UPDATE quizzes SET status='draft' WHERE id=?",(self.quiz_id,))
        self.assertEqual(self.submit()[0],409)

    def test_failed_result_write_rolls_back_answers_and_allows_retry(self):
        with connect(self.database) as db:db.execute("CREATE TRIGGER fail_score BEFORE INSERT ON quiz_attempt_results BEGIN SELECT RAISE(ABORT,'score test failure'); END")
        self.assertEqual(self.submit()[0],500)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempt_answers').fetchone()[0],0)
            self.assertIsNone(db.execute('SELECT submitted_at FROM quiz_attempts WHERE id=?',(self.attempt,)).fetchone()[0])
            db.execute('DROP TRIGGER fail_score')
        self.assertEqual(self.submit()[0],200)

    def test_success_is_committed_before_http_confirmation(self):
        original=server.Handler.json;observed=[]
        def before_send(handler,status,data,extra=None):
            if status==200 and data.get('submitted'):
                with connect(self.database) as db:observed.append(db.execute('SELECT score FROM quiz_attempt_results WHERE attempt_id=?',(self.attempt,)).fetchone()[0])
            return original(handler,status,data,extra)
        with patch.object(server.Handler,'json',before_send):self.assertEqual(self.submit()[0],200)
        self.assertEqual(observed,[2])

    def test_receipt_is_private_and_contains_no_grading_snapshot_or_keys(self):
        self.assertEqual(self.result()[0],409)
        data=self.submit()[1]
        for secret in ['grading_snapshot','correct_option_id','is_correct','password_hash','token_hash']:
            self.assertNotIn(secret,json.dumps(data))
            self.assertNotIn(secret,json.dumps(self.started))
        self.assertEqual(self.result()[1]['result'],data['result'])

    def test_legacy_attempts_and_saved_answers_are_preserved_without_invented_grades(self):
        with connect(self.database) as db:
            active=db.execute('INSERT INTO quiz_attempts(quiz_id,student_id) VALUES(?,2)',(self.quiz_id,)).lastrowid
            old=db.execute("INSERT INTO quiz_attempts(quiz_id,student_id,submitted_at) VALUES(?,2,'2026-10-01 10:00:00')",(self.quiz_id,)).lastrowid
            db.execute('INSERT INTO quiz_attempt_answers VALUES(?,?,?)',(old,self.correct[0]['question_id'],self.correct[0]['option_id']))
        self.assertEqual(self.submit(attempt=active)[0],409)
        status,data,_=self.submit(attempt=old)
        self.assertEqual(status,200);self.assertTrue(data['already_submitted']);self.assertIsNone(data['result'])
        self.assertEqual(len(data['answers']),1)
        initialize(self.database)
        with connect(self.database) as db:self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempt_results').fetchone()[0],0)

    def test_grading_snapshot_and_receipt_survive_backup_restore(self):
        from study_platform.recovery import create_backup,restore_backup
        self.submit();storage=self.database.parent/'files';storage.mkdir(mode=0o700)
        backup=create_backup(self.database,storage,self.database.parent/'backups')
        with connect(self.database) as db:db.execute('DELETE FROM quiz_attempt_results')
        restore_backup(backup,self.database,storage)
        initialize(self.database)
        self.assertEqual(self.result()[1]['result']['score'],2)

    def test_fresh_role_recheck_rejects_stale_student_context(self):
        with connect(self.database) as db:db.execute("UPDATE users SET role='instructor' WHERE id=2")
        with self.assertRaises(APIError) as caught:
            with connect(self.database) as db:submit_attempt(db,{'id':2,'role':'student'},self.attempt,{'answers':self.correct})
        self.assertEqual(caught.exception.status,403)


    def test_additive_migration_keeps_pre_scoring_attempts_and_new_attempts_can_grade(self):
        with connect(self.database) as db:
            before=db.execute('SELECT id,student_id,quiz_id,started_at FROM quiz_attempts WHERE id=?',(self.attempt,)).fetchone()[:]
            db.execute('ALTER TABLE quiz_attempts DROP COLUMN grading_snapshot')
        initialize(self.database);initialize(self.database)
        with connect(self.database) as db:
            after=db.execute('SELECT id,student_id,quiz_id,started_at FROM quiz_attempts WHERE id=?',(self.attempt,)).fetchone()[:]
            self.assertEqual(before,after)
            self.assertIsNone(db.execute('SELECT grading_snapshot FROM quiz_attempts WHERE id=?',(self.attempt,)).fetchone()[0])
            fresh=start_quiz_attempt(db,{'id':2,'role':'student'},self.quiz_id)['attempt_id']
        self.assertEqual(self.submit(attempt=self.attempt)[0],409)
        self.assertEqual(self.submit(attempt=fresh)[1]['result']['score'],2)

    def test_start_rejects_broken_answer_keys_without_creating_an_attempt(self):
        with connect(self.database) as db:db.execute('UPDATE quiz_options SET is_correct=0')
        status,_,_=self.request('POST',f'/api/quizzes/{self.quiz_id}/attempts',{})
        self.assertEqual(status,409)
        with connect(self.database) as db:self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempts').fetchone()[0],1)

    def test_concurrent_different_payloads_cannot_overwrite_the_first_grade(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda answers:self.submit(answers),[self.correct,[]]))
        self.assertEqual([item[0] for item in responses],[200,200])
        self.assertEqual(responses[0][1]['result'],responses[1][1]['result'])
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM quiz_attempt_results').fetchone()[0],1)
            row=db.execute('SELECT score,answered_count FROM quiz_attempt_results').fetchone()
            self.assertEqual((row['score'],row['answered_count']),(2,2) if row['score'] else (0,0))
