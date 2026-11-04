"""Issue #13: Quiz creation and validation tests."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from server import Handler
from study_platform.db import connect, initialize
from study_platform.demo import seed


class MemoryConnection:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()

    def makefile(self, *args, **kwargs):
        return self.input

    def sendall(self, data):
        self.output.write(data)


class QuizTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / 'quiz.db'
        initialize(self.database)

        with connect(self.database) as db:
            seed(db)

        self.server = SimpleNamespace(database=self.database, demo=True)
        self.cookie = ''
        self.csrf = ''

    def tearDown(self):
        self.temp.cleanup()

    def login_sample(self, user_id):
        status, body = self.request(
            'POST', '/api/demo/session', {'user_id': user_id}
        )
        self.assertEqual(status, 200)
        headers = self._last_headers
        self.cookie = headers['Set-Cookie'].split(';')[0]
        self.csrf = body['csrf_token']

    def request(self, method, path, data=None):
        headers = {
            'Host': '127.0.0.1:8000',
            'Connection': 'close',
            'Cookie': self.cookie,
            'X-CSRF-Token': self.csrf,
        }

        body = b'' if data is None else json.dumps(data).encode()
        if data is not None:
            headers['Content-Type'] = 'application/json'
            headers['Content-Length'] = str(len(body))

        raw_request = (
            f'{method} {path} HTTP/1.1\r\n'
            + ''.join(f'{key}: {value}\r\n' for key, value in headers.items())
            + '\r\n'
        ).encode() + body

        connection = MemoryConnection(raw_request)
        Handler(connection, ('127.0.0.1', 12345), self.server)

        head, content = connection.output.getvalue().split(b'\r\n\r\n', 1)
        lines = head.decode().split('\r\n')
        status = int(lines[0].split()[1])
        response_headers = dict(
            line.split(': ', 1) for line in lines[1:]
        )
        self._last_headers = response_headers

        if content and response_headers.get('Content-Type', '').startswith(
            'application/json'
        ):
            content = json.loads(content)

        return status, content

    def valid_quiz(self):
        return {
            'title': 'Database Fundamentals',
            'questions': [
                {
                    'question': 'What does SQL stand for?',
                    'options': [
                        {'text': 'Structured Query Language', 'is_correct': True},
                        {'text': 'Simple Question Language', 'is_correct': False},
                    ],
                },
                {
                    'question': 'Which command retrieves data?',
                    'options': [
                        {'text': 'INSERT', 'is_correct': False},
                        {'text': 'SELECT', 'is_correct': True},
                    ],
                },
            ],
        }

    def test_instructor_can_create_quiz(self):
        self.login_sample(1)

        status, body = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )

        self.assertEqual(status, 201)
        self.assertEqual(body['quiz']['title'], 'Database Fundamentals')
        self.assertEqual(body['quiz']['question_count'], 2)

        with connect(self.database) as db:
            quiz = db.execute(
                'SELECT * FROM quizzes WHERE id=?',
                (body['quiz']['id'],)
            ).fetchone()

            self.assertIsNotNone(quiz)
            self.assertEqual(
                db.execute(
                    'SELECT COUNT(*) FROM quiz_questions WHERE quiz_id=?',
                    (quiz['id'],)
                ).fetchone()[0],
                2
            )

            self.assertEqual(
                db.execute(
                    '''SELECT COUNT(*) FROM quiz_options o
                       JOIN quiz_questions q ON q.id=o.question_id
                       WHERE q.quiz_id=?''',
                    (quiz['id'],)
                ).fetchone()[0],
                4
            )

    def test_empty_question_is_rejected(self):
        self.login_sample(1)
        quiz = self.valid_quiz()
        quiz['questions'][0]['question'] = '   '

        status, _ = self.request('POST', '/api/groups/1/quizzes', quiz)
        self.assertEqual(status, 400)

    def test_question_needs_at_least_two_options(self):
        self.login_sample(1)
        quiz = self.valid_quiz()
        quiz['questions'][0]['options'] = [
            {'text': 'Only option', 'is_correct': True}
        ]

        status, _ = self.request('POST', '/api/groups/1/quizzes', quiz)
        self.assertEqual(status, 400)

    def test_question_needs_exactly_one_correct_answer(self):
        self.login_sample(1)

        for correct_values in [
            [False, False],
            [True, True],
        ]:
            quiz = self.valid_quiz()
            quiz['questions'][0]['options'][0]['is_correct'] = correct_values[0]
            quiz['questions'][0]['options'][1]['is_correct'] = correct_values[1]

            status, _ = self.request(
                'POST', '/api/groups/1/quizzes', quiz
            )
            self.assertEqual(status, 400)

    def test_empty_option_is_rejected(self):
        self.login_sample(1)
        quiz = self.valid_quiz()
        quiz['questions'][0]['options'][0]['text'] = '  '

        status, _ = self.request('POST', '/api/groups/1/quizzes', quiz)
        self.assertEqual(status, 400)

    def test_student_cannot_create_quiz(self):
        self.login_sample(2)

        status, _ = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )

        self.assertEqual(status, 403)

    def test_instructor_cannot_create_quiz_in_another_instructors_group(self):
        self.login_sample(1)

        status, _ = self.request(
            'POST', '/api/groups/3/quizzes', self.valid_quiz()
        )

        self.assertEqual(status, 403)


    def test_student_can_view_quiz_without_correct_answers(self):
        self.login_sample(1)
        status, created = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )
        self.assertEqual(status, 201)

        quiz_id = created['quiz']['id']

        # Instructor publishes the quiz.
        status, published = self.request(
            'POST', f'/api/quizzes/{quiz_id}/publish', {}
        )
        self.assertEqual(status, 200)
        self.assertEqual(published['quiz']['status'], 'published')

        # Student can now view the published quiz.
        self.login_sample(2)
        status, result = self.request('GET', '/api/groups/1/quizzes')
        self.assertEqual(status, 200)
        self.assertEqual(len(result['quizzes']), 1)

        quiz = result['quizzes'][0]
        self.assertEqual(quiz['title'], 'Database Fundamentals')
        self.assertEqual(len(quiz['questions']), 2)

        for question in quiz['questions']:
            self.assertGreaterEqual(len(question['options']), 2)
            for option in question['options']:
                self.assertIn('id', option)
                self.assertIn('text', option)
                self.assertNotIn('is_correct', option)

    def test_student_cannot_view_unpublished_quiz(self):
        self.login_sample(1)

        status, created = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )
        self.assertEqual(status, 201)

        self.login_sample(2)
        status, result = self.request('GET', '/api/groups/1/quizzes')

        self.assertEqual(status, 200)
        self.assertEqual(len(result['quizzes']), 0)

    def test_student_cannot_publish_quiz(self):
        self.login_sample(1)

        status, created = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )
        self.assertEqual(status, 201)

        quiz_id = created['quiz']['id']

        self.login_sample(2)
        status, _ = self.request(
            'POST', f'/api/quizzes/{quiz_id}/publish', {}
        )

        self.assertEqual(status, 403)

    def test_incomplete_quiz_cannot_be_published(self):
        self.login_sample(1)

        status, created = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )
        self.assertEqual(status, 201)

        quiz_id = created['quiz']['id']

        # Simulate an incomplete quiz by removing an option.
        with connect(self.database) as db:
            question_id = db.execute(
                'SELECT id FROM quiz_questions WHERE quiz_id=? ORDER BY position LIMIT 1',
                (quiz_id,)
            ).fetchone()['id']

            db.execute(
                'DELETE FROM quiz_options WHERE question_id=? '
                'AND id=(SELECT MAX(id) FROM quiz_options WHERE question_id=?)',
                (question_id, question_id)
            )

        status, _ = self.request(
            'POST', f'/api/quizzes/{quiz_id}/publish', {}
        )

        self.assertEqual(status, 400)

        with connect(self.database) as db:
            quiz = db.execute(
                'SELECT status FROM quizzes WHERE id=?', (quiz_id,)
            ).fetchone()

            self.assertEqual(quiz['status'], 'draft')

    def test_student_cannot_view_quizzes_from_another_group(self):
        self.login_sample(4)

        status, _ = self.request('GET', '/api/groups/1/quizzes')

        self.assertEqual(status, 403)

    def test_quiz_retrieval_does_not_expose_correct_answer_field(self):
        self.login_sample(1)
        status, _ = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )
        self.assertEqual(status, 201)

        status, result = self.request('GET', '/api/groups/1/quizzes')

        self.assertEqual(status, 200)
        self.assertNotIn('is_correct', json.dumps(result))


    def test_unauthenticated_and_missing_csrf_requests_are_denied(self):
        self.assertEqual(self.request('GET','/api/groups/1/quizzes')[0],401)
        self.assertEqual(self.request('POST','/api/groups/1/quizzes',self.valid_quiz())[0],401)
        self.login_sample(1); self.csrf = 'wrong'
        self.assertEqual(self.request('POST','/api/groups/1/quizzes',self.valid_quiz())[0],403)

    def test_invalid_text_and_payload_types_are_rejected_without_partial_records(self):
        self.login_sample(1)
        for field,value in [('title','\ud800'),('title','bad\x00title'),('title','x'*161),('question','q'*1001),('question','\ud800'),('option','o'*501),('option','\ud800')]:
            quiz=self.valid_quiz()
            if field=='title': quiz['title']=value
            elif field=='question': quiz['questions'][0]['question']=value
            else: quiz['questions'][0]['options'][0]['text']=value
            self.assertEqual(self.request('POST','/api/groups/1/quizzes',quiz)[0],400)
        quiz=self.valid_quiz();quiz['questions'][0]['options'][0]['is_correct']='true'
        self.assertEqual(self.request('POST','/api/groups/1/quizzes',quiz)[0],400)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM quizzes').fetchone()[0],0)

    def test_database_failure_rolls_back_quiz_questions_and_options(self):
        self.login_sample(1)
        with connect(self.database) as db:
            db.execute("CREATE TRIGGER reject_quiz_option BEFORE INSERT ON quiz_options BEGIN SELECT RAISE(ABORT,'test failure'); END")
        self.assertEqual(self.request('POST','/api/groups/1/quizzes',self.valid_quiz())[0],400)
        with connect(self.database) as db:
            for table in ['quizzes','quiz_questions','quiz_options']:
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_stale_author_role_cannot_create_quiz_after_revocation(self):
        from study_platform.quizzes import create_quiz
        from study_platform.security import APIError
        with connect(self.database) as db:
            db.execute("UPDATE users SET role='student' WHERE id=1")
        with self.assertRaises(APIError) as error:
            with connect(self.database) as db:
                create_quiz(db,{'id':1,'role':'instructor'},1,self.valid_quiz())
        self.assertEqual(error.exception.status,403)
    def test_student_can_start_published_quiz_without_correct_answers(self):
        self.login_sample(1)
        status, created = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )
        self.assertEqual(status, 201)

        quiz_id = created['quiz']['id']
        status, _ = self.request(
            'POST', f'/api/quizzes/{quiz_id}/publish'
        )
        self.assertEqual(status, 200)

        self.login_sample(2)

        status, result = self.request(
            'POST', f'/api/quizzes/{quiz_id}/attempts'
        )

        self.assertEqual(status, 201)
        self.assertIn('attempt_id', result)
        self.assertEqual(result['quiz']['title'], 'Database Fundamentals')

        for question in result['quiz']['questions']:
            for option in question['options']:
                self.assertNotIn('is_correct', option)

    def test_student_cannot_start_draft_quiz(self):
        self.login_sample(1)

        status, created = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )
        self.assertEqual(status, 201)

        quiz_id = created['quiz']['id']
        self.login_sample(2)

        status, _ = self.request(
            'POST', f'/api/quizzes/{quiz_id}/attempts'
        )

        self.assertEqual(status, 404)

    def test_student_can_submit_quiz_answers(self):
        self.login_sample(1)

        status, created = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )
        self.assertEqual(status, 201)

        quiz_id = created['quiz']['id']

        status, _ = self.request(
            'POST', f'/api/quizzes/{quiz_id}/publish'
        )
        self.assertEqual(status, 200)

        self.login_sample(2)

        status, started = self.request(
            'POST', f'/api/quizzes/{quiz_id}/attempts'
        )
        self.assertEqual(status, 201)

        answers = [
            {
                'question_id': question['id'],
                'option_id': question['options'][0]['id']
            }
            for question in started['quiz']['questions']
        ]

        status, result = self.request(
            'POST',
            f"/api/quiz-attempts/{started['attempt_id']}/submit",
            {'answers': answers}
        )

        self.assertEqual(status, 200)
        self.assertTrue(result['submitted'])
    def test_student_cannot_start_quiz_from_another_group(self):
        self.login_sample(1)

        status, created = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )
        self.assertEqual(status, 201)

        quiz_id = created['quiz']['id']

        self.request('POST', f'/api/quizzes/{quiz_id}/publish')

        # Log in as a student who does not belong to this group.
        self.login_sample(3)

        status, _ = self.request(
            'POST', f'/api/quizzes/{quiz_id}/attempts'
        )

        self.assertEqual(status, 403)

    def test_student_cannot_submit_another_students_attempt(self):
        self.login_sample(1)

        status, created = self.request(
            'POST', '/api/groups/1/quizzes', self.valid_quiz()
        )
        self.assertEqual(status, 201)

        quiz_id = created['quiz']['id']
        self.request('POST', f'/api/quizzes/{quiz_id}/publish')

        self.login_sample(2)

        status, started = self.request(
            'POST', f'/api/quizzes/{quiz_id}/attempts'
        )
        self.assertEqual(status, 201)

        attempt_id = started['attempt_id']

        # Switch to a different student.
        self.login_sample(3)

        status, _ = self.request(
            'POST',
            f'/api/quiz-attempts/{attempt_id}/submit',
            {'answers': []}
        )

        self.assertEqual(status, 403)


    def test_quiz_and_upload_recovery_schemas_coexist(self):
        from study_platform.recovery import create_backup,restore_backup
        self.login_sample(1)
        self.assertEqual(self.request('POST','/api/groups/1/quizzes',self.valid_quiz())[0],201)
        storage=Path(self.temp.name)/'files';storage.mkdir(mode=0o700)
        (storage/'notes.txt').write_text('Saved academic material')
        backup=create_backup(self.database,storage,Path(self.temp.name)/'backups')
        with connect(self.database) as db:db.execute('DELETE FROM quizzes')
        restore_backup(backup,self.database,storage)
        with connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM quizzes').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM quiz_options WHERE is_correct=1').fetchone()[0],2)
            self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='upload_idempotency'").fetchone())
        self.assertEqual((storage/'notes.txt').read_text(),'Saved academic material')

    def _submitted_result(self):
        self.login_sample(1)
        status,created=self.request('POST','/api/groups/1/quizzes',self.valid_quiz())
        self.assertEqual(status,201)
        quiz_id=created['quiz']['id']
        self.assertEqual(self.request('POST',f'/api/quizzes/{quiz_id}/publish',{})[0],200)
        self.login_sample(2)
        status,started=self.request('POST',f'/api/quizzes/{quiz_id}/attempts',{})
        self.assertEqual(status,201)
        questions=started['quiz']['questions']
        answers=[{'question_id':question['id'],'option_id':question['options'][index]['id']} for index,question in enumerate(questions)]
        status,receipt=self.request('POST',f"/api/quiz-attempts/{started['attempt_id']}/submit",{'answers':answers})
        self.assertEqual(status,200)
        return receipt

    def test_student_can_submit_quiz_and_view_own_result(self):
        receipt=self._submitted_result()
        self.assertEqual(receipt['result']['score'],2)
        status,results=self.request('GET','/api/results/me')
        self.assertEqual(status,200);self.assertEqual(len(results['results']),1)
        self.assertEqual(results['results'][0]['quiz_title'],'Database Fundamentals')
        self.assertEqual(results['results'][0]['score'],2)
        self.assertEqual(results['results'][0]['percentage'],100)
        self.login_sample(4)
        self.assertEqual(self.request('GET','/api/results/me')[1]['results'],[])

    def test_instructor_can_view_group_quiz_results(self):
        self._submitted_result();self.login_sample(1)
        status,results=self.request('GET','/api/groups/1/results')
        self.assertEqual(status,200);self.assertEqual(len(results['results']),1)
        self.assertEqual(results['results'][0]['score'],2)
        self.assertEqual(results['results'][0]['student_name'],'Demo Student')

    def test_student_cannot_view_group_results(self):
        self.login_sample(2)

        status, _ = self.request(
            'GET', '/api/groups/1/results'
        )

        self.assertEqual(status, 403)

    def test_instructor_cannot_view_unmanaged_group_results(self):
        self.login_sample(1)

        status, _ = self.request(
            'GET', '/api/groups/3/results'
        )

        self.assertEqual(status, 403)