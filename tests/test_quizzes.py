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

        if content and response_headers.get('Content-Type', '').startswith(
            'application/json'
        ):
            content = json.loads(content)

        return status, content

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


if __name__ == '__main__':
    unittest.main()
