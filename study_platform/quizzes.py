"""Quiz creation and question validation."""
import sqlite3

from .security import APIError, group_access, require_permission



def _text(value, maximum, message):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum or '\x00' in value:
        raise APIError(400, message)
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise APIError(400, message)
    return value.strip()


def create_quiz(db, user, group_id, data):
    require_permission(user, 'quiz.create')

    if not isinstance(data, dict):
        raise APIError(400, 'Expected a quiz details object.')

    title = _text(data.get('title'), 160, 'Quiz title must contain 1–160 valid characters.')

    questions = data.get('questions')
    if not isinstance(questions, list) or not 1 <= len(questions) <= 100:
        raise APIError(400, 'Add between 1 and 100 questions to the quiz.')

    validated_questions = []

    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise APIError(400, f'Question {index} is invalid.')

        question_text = _text(question.get('question'), 1000,
                              f'Question {index} needs 1–1000 valid characters of question text.')

        options = question.get('options')
        if not isinstance(options, list) or not 2 <= len(options) <= 20:
            raise APIError(400, f'Question {index} needs between two and twenty options.')

        validated_options = []
        correct_count = 0

        for option_index, option in enumerate(options, start=1):
            if not isinstance(option, dict):
                raise APIError(
                    400, f'Option {option_index} in question {index} is invalid.'
                )

            option_text = _text(option.get('text'), 500,
                                f'Option {option_index} in question {index} needs 1–500 valid characters.')
            is_correct = option.get('is_correct', False)

            if type(is_correct) is not bool:
                raise APIError(
                    400, f'Correct-answer selection in question {index} must be true or false.'
                )

            if is_correct:
                correct_count += 1

            validated_options.append((option_text.strip(), int(is_correct)))

        if correct_count != 1:
            raise APIError(
                400, f'Question {index} must have exactly one correct answer.'
            )

        validated_questions.append(
            (question_text.strip(), validated_options)
        )

    # Lock the write transaction while checking access and saving the quiz.
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')

    current = db.execute('SELECT id,role,is_active FROM users WHERE id=?', (user['id'],)).fetchone()
    if current is None or not current['is_active']:
        raise APIError(401, 'Your account is unavailable. Sign in again.')
    require_permission(current, 'quiz.create')
    group_access(db, current, group_id, manage=True)

    try:
        quiz_cursor = db.execute(
            '''INSERT INTO quizzes (group_id, created_by, title)
               VALUES (?, ?, ?)''',
            (group_id, user['id'], title.strip())
        )
        quiz_id = quiz_cursor.lastrowid

        for position, (question_text, options) in enumerate(validated_questions):
            question_cursor = db.execute(
                '''INSERT INTO quiz_questions (quiz_id, question_text, position)
                   VALUES (?, ?, ?)''',
                (quiz_id, question_text, position)
            )
            question_id = question_cursor.lastrowid

            db.executemany(
                '''INSERT INTO quiz_options
                   (question_id, option_text, is_correct)
                   VALUES (?, ?, ?)''',
                [
                    (question_id, option_text, is_correct)
                    for option_text, is_correct in options
                ]
            )

    except sqlite3.IntegrityError as exc:
        raise APIError(400, 'Quiz could not be saved. Check the supplied details.') from exc

    return {
        'id': quiz_id,
        'group_id': group_id,
        'title': title.strip(),
        'question_count': len(validated_questions),
        'message': 'Quiz created successfully.'
    }


def publish_quiz(db, user, quiz_id):
    """Publish a complete quiz after verifying instructor access."""
    require_permission(user, 'quiz.create')

    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')

    current = db.execute(
        'SELECT id, role, is_active FROM users WHERE id=?',
        (user['id'],)
    ).fetchone()

    if current is None or not current['is_active']:
        raise APIError(401, 'Your account is unavailable. Sign in again.')

    require_permission(current, 'quiz.create')

    quiz = db.execute(
        'SELECT id, group_id, title, status FROM quizzes WHERE id=?',
        (quiz_id,)
    ).fetchone()

    if quiz is None:
        raise APIError(404, 'Quiz not found.')

    group_access(db, current, quiz['group_id'], manage=True)

    questions = db.execute(
        '''SELECT id, question_text
           FROM quiz_questions
           WHERE quiz_id=?
           ORDER BY position''',
        (quiz_id,)
    ).fetchall()

    if not questions:
        raise APIError(400, 'Add at least one question before publishing.')

    for index, question in enumerate(questions, start=1):
        if not question['question_text'].strip():
            raise APIError(400, f'Question {index} is incomplete.')

        options = db.execute(
            '''SELECT option_text, is_correct
               FROM quiz_options
               WHERE question_id=?
               ORDER BY id''',
            (question['id'],)
        ).fetchall()

        if not 2 <= len(options) <= 20:
            raise APIError(
                400, f'Question {index} must have between two and twenty options.'
            )

        if any(not option['option_text'].strip() for option in options):
            raise APIError(400, f'Question {index} has an empty option.')

        if sum(option['is_correct'] for option in options) != 1:
            raise APIError(
                400, f'Question {index} must have exactly one correct answer.'
            )

    db.execute(
        "UPDATE quizzes SET status='published' WHERE id=?",
        (quiz_id,)
    )

    return {
        'id': quiz['id'],
        'group_id': quiz['group_id'],
        'title': quiz['title'],
        'status': 'published',
        'message': 'Quiz published successfully.'
    }


def list_group_quizzes(db, user, group_id):
    """Return quizzes the current user is allowed to see."""
    require_permission(user, 'groups.read')
    group = group_access(db, user, group_id)

    can_manage = (
        user['role'] == 'administrator'
        or (
            user['role'] == 'instructor'
            and group['created_by'] == user['id']
        )
    )

    if can_manage:
        quizzes = db.execute(
            '''SELECT id, title, status, created_at
               FROM quizzes
               WHERE group_id = ?
               ORDER BY id''',
            (group_id,)
        ).fetchall()
    else:
        quizzes = db.execute(
            '''SELECT id, title, status, created_at
               FROM quizzes
               WHERE group_id = ? AND status = 'published'
               ORDER BY id''',
            (group_id,)
        ).fetchall()

    results = []

    for quiz in quizzes:
        questions = db.execute(
            '''SELECT id, question_text, position
               FROM quiz_questions
               WHERE quiz_id = ?
               ORDER BY position''',
            (quiz['id'],)
        ).fetchall()

        question_results = []

        for question in questions:
            options = db.execute(
                '''SELECT id, option_text
                   FROM quiz_options
                   WHERE question_id = ?
                   ORDER BY id''',
                (question['id'],)
            ).fetchall()

            question_results.append({
                'id': question['id'],
                'question': question['question_text'],
                'options': [
                    {'id': option['id'], 'text': option['option_text']}
                    for option in options
                ]
            })

        results.append({
            'id': quiz['id'],
            'title': quiz['title'],
            'status': quiz['status'],
            'questions': question_results
        })

    return {'group': group, 'quizzes': results}


def start_quiz_attempt(db, user, quiz_id):
    """Start an attempt for a published quiz as an eligible student."""
    if user['role'] != 'student':
        raise APIError(403, 'Only students can attempt quizzes')

    quiz = db.execute(
        '''
        SELECT q.id, q.group_id, q.title, q.status
        FROM quizzes q
        WHERE q.id = ?
        ''',
        (quiz_id,)
    ).fetchone()

    if not quiz or quiz['status'] != 'published':
        raise APIError(404, 'Published quiz not found')

    group_access(db, user, quiz['group_id'])

    cursor = db.execute(
        '''
        INSERT INTO quiz_attempts (quiz_id, student_id)
        VALUES (?, ?)
        ''',
        (quiz_id, user['id'])
    )

    attempt_id = cursor.lastrowid

    questions = db.execute(
        '''
        SELECT id, question_text
        FROM quiz_questions
        WHERE quiz_id = ?
        ORDER BY position
        ''',
        (quiz_id,)
    ).fetchall()

    result_questions = []

    for question in questions:
        options = db.execute(
            '''
            SELECT id, option_text
            FROM quiz_options
            WHERE question_id = ?
            ORDER BY id
            ''',
            (question['id'],)
        ).fetchall()

        result_questions.append({
            'id': question['id'],
            'question': question['question_text'],
            'options': [
                {'id': option['id'], 'text': option['option_text']}
                for option in options
            ]
        })

    return {
        'attempt_id': attempt_id,
        'quiz': {
            'id': quiz['id'],
            'title': quiz['title'],
            'questions': result_questions
        }
    }


def submit_quiz_attempt(db, user, attempt_id, data):
    """Save a student's final answers and submit their attempt."""
    if user['role'] != 'student':
        raise APIError(403, 'Only students can submit quiz attempts')

    attempt = db.execute(
        '''
        SELECT id, quiz_id, student_id, submitted_at
        FROM quiz_attempts
        WHERE id = ?
        ''',
        (attempt_id,)
    ).fetchone()

    if not attempt or attempt['student_id'] != user['id']:
        raise APIError(404, 'Quiz attempt not found')

    if attempt['submitted_at']:
        raise APIError(409, 'This quiz attempt has already been submitted')

    answers = data.get('answers')

    if not isinstance(answers, list):
        raise APIError(400, 'Answers must be provided as a list')

    questions = db.execute(
        '''
        SELECT id
        FROM quiz_questions
        WHERE quiz_id = ?
        ''',
        (attempt['quiz_id'],)
    ).fetchall()

    question_ids = {question['id'] for question in questions}
    submitted_question_ids = set()

    for answer in answers:
        if not isinstance(answer, dict):
            raise APIError(400, 'Each answer must be an object')

        question_id = answer.get('question_id')
        option_id = answer.get('option_id')

        if (
            not isinstance(question_id, int)
            or isinstance(question_id, bool)
            or not isinstance(option_id, int)
            or isinstance(option_id, bool)
        ):
            raise APIError(400, 'Invalid question or option ID')

        if question_id not in question_ids or question_id in submitted_question_ids:
            raise APIError(400, 'Invalid or duplicate question answer')

        valid_option = db.execute(
            '''
            SELECT id
            FROM quiz_options
            WHERE id = ? AND question_id = ?
            ''',
            (option_id, question_id)
        ).fetchone()

        if not valid_option:
            raise APIError(400, 'Selected option does not belong to this question')

        submitted_question_ids.add(question_id)

    for answer in answers:
        db.execute(
            '''
            INSERT INTO quiz_attempt_answers (attempt_id, question_id, option_id)
            VALUES (?, ?, ?)
            ''',
            (attempt_id, answer['question_id'], answer['option_id'])
        )

    db.execute(
        '''
        UPDATE quiz_attempts
        SET submitted_at = CURRENT_TIMESTAMP
        WHERE id = ? AND submitted_at IS NULL
        ''',
        (attempt_id,)
    )

    return {'attempt_id': attempt_id, 'submitted': True}