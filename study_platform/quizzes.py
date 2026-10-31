"""Quiz creation and question validation."""
import sqlite3

from .security import APIError, group_access, require_permission


def create_quiz(db, user, group_id, data):
    require_permission(user, 'quiz.create')

    if not isinstance(data, dict):
        raise APIError(400, 'Expected a quiz details object.')

    title = data.get('title')
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160:
        raise APIError(400, 'Quiz title must contain 1–160 characters.')

    questions = data.get('questions')
    if not isinstance(questions, list) or not questions:
        raise APIError(400, 'Add at least one question to the quiz.')

    validated_questions = []

    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise APIError(400, f'Question {index} is invalid.')

        question_text = question.get('question')
        if not isinstance(question_text, str) or not question_text.strip():
            raise APIError(400, f'Question {index} needs question text.')

        options = question.get('options')
        if not isinstance(options, list) or len(options) < 2:
            raise APIError(400, f'Question {index} needs at least two options.')

        validated_options = []
        correct_count = 0

        for option_index, option in enumerate(options, start=1):
            if not isinstance(option, dict):
                raise APIError(
                    400, f'Option {option_index} in question {index} is invalid.'
                )

            option_text = option.get('text')
            is_correct = option.get('is_correct', False)

            if not isinstance(option_text, str) or not option_text.strip():
                raise APIError(
                    400, f'Option {option_index} in question {index} cannot be empty.'
                )

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

    group_access(db, user, group_id, manage=True)

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


def list_group_quizzes(db, user, group_id):
    """Return group quizzes without exposing correct-answer information."""
    require_permission(user, 'groups.read')
    group = group_access(db, user, group_id)

    quizzes = db.execute(
        '''SELECT id, title, created_at
           FROM quizzes
           WHERE group_id = ?
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
            'questions': question_results
        })

    return {'group': group, 'quizzes': results}
