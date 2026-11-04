"""Issue #16: frozen MCQ grading, private receipts and atomic final submission."""
import json
from .security import APIError, group_access, require_permission

MAX_ID = 9223372036854775807
SCHEMA = """
CREATE TABLE IF NOT EXISTS quiz_attempt_results (
    attempt_id INTEGER PRIMARY KEY REFERENCES quiz_attempts(id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK(typeof(score)='integer' AND score>=0),
    max_score INTEGER NOT NULL CHECK(typeof(max_score)='integer' AND max_score BETWEEN 1 AND 100),
    answered_count INTEGER NOT NULL CHECK(typeof(answered_count)='integer' AND answered_count>=0),
    submitted_at TEXT NOT NULL,
    CHECK(score<=answered_count AND answered_count<=max_score)
);
"""


def parse_quiz_id(raw):
    if len(raw) > 19 or int(raw) > MAX_ID:
        raise APIError(400, 'Invalid quiz or attempt ID.')
    return int(raw)


def student_account(db, user):
    current = db.execute('SELECT id,role,is_active FROM users WHERE id=?', (user['id'],)).fetchone()
    if current is None or not current['is_active']:
        raise APIError(401, 'Your account is unavailable. Sign in again.')
    require_permission(current, 'quiz.attempt')
    if current['role'] != 'student':
        raise APIError(403, 'Only students can use quiz attempts.')
    return current


def freeze_questions(db, quiz):
    """Keep the exact questions/options and private key used when starting."""
    rows = db.execute('SELECT id,question_text FROM quiz_questions WHERE quiz_id=? ORDER BY position,id', (quiz['id'],)).fetchall()
    if not 1 <= len(rows) <= 100:
        raise APIError(409, 'This quiz needs valid questions before it can be attempted.')
    questions = []
    for question in rows:
        options = db.execute('SELECT id,option_text,is_correct FROM quiz_options WHERE question_id=? ORDER BY id', (question['id'],)).fetchall()
        keys = [option['id'] for option in options if option['is_correct'] == 1]
        if not 1 <= question['id'] <= MAX_ID or any(not 1 <= option['id'] <= MAX_ID for option in options) or not 2 <= len(options) <= 20 or len(keys) != 1 or not question['question_text'].strip() or any(not option['option_text'].strip() for option in options):
            raise APIError(409, 'This quiz needs valid questions before it can be attempted.')
        questions.append({'id': question['id'], 'question': question['question_text'],
                          'options': [{'id': option['id'], 'text': option['option_text']} for option in options],
                          'correct_option_id': keys[0]})
    return {'version': 1, 'quiz_id': quiz['id'], 'group_id': quiz['group_id'],
            'title': quiz['title'], 'questions': questions}


def public_questions(snapshot):
    return [{key: question[key] for key in ('id', 'question', 'options')} for question in snapshot['questions']]


def owned_attempt(db, user, attempt_id):
    student = student_account(db, user)
    row = db.execute('''SELECT a.*,q.group_id,q.status AS quiz_status
        FROM quiz_attempts a JOIN quizzes q ON q.id=a.quiz_id
        WHERE a.id=? AND a.student_id=?''', (attempt_id, student['id'])).fetchone()
    if row is None:
        raise APIError(404, 'Quiz attempt not found.')
    group_access(db, student, row['group_id'])
    return row


def receipt(db, attempt):
    result = db.execute('SELECT score,max_score,answered_count,submitted_at FROM quiz_attempt_results WHERE attempt_id=?', (attempt['id'],)).fetchone()
    answers = [dict(row) for row in db.execute('SELECT question_id,option_id FROM quiz_attempt_answers WHERE attempt_id=? ORDER BY question_id', (attempt['id'],))]
    summary = None
    if result is not None:
        summary = dict(result)
        summary['unanswered_count'] = result['max_score'] - result['answered_count']
    return {'attempt_id': attempt['id'], 'quiz_id': attempt['quiz_id'], 'student_id': attempt['student_id'],
            'submitted': True, 'result': summary, 'answers': answers}


def get_result(db, user, attempt_id):
    attempt = owned_attempt(db, user, attempt_id)
    if attempt['submitted_at'] is None:
        raise APIError(409, 'This attempt has not been submitted yet.')
    if attempt['grading_snapshot'] is not None and not db.execute('SELECT 1 FROM quiz_attempt_results WHERE attempt_id=?', (attempt_id,)).fetchone():
        raise APIError(409, 'The saved result is unavailable. Your submitted answers have been preserved.')
    return receipt(db, attempt)


def _snapshot(db, attempt):
    if attempt['grading_snapshot'] is None:
        raise APIError(409, 'This attempt started before scoring was available. Close it and start a new attempt; existing answers are preserved.')
    try:
        snapshot = json.loads(attempt['grading_snapshot'])
        questions = snapshot['questions']
        if snapshot['version'] != 1 or snapshot['quiz_id'] != attempt['quiz_id'] or snapshot['group_id'] != attempt['group_id'] or not isinstance(questions, list) or not 1 <= len(questions) <= 100:
            raise ValueError()
        ids = set()
        for question in questions:
            qid = question['id']; options = question['options']; key = question['correct_option_id']
            if type(qid) is not int or not 1 <= qid <= MAX_ID or qid in ids or not 2 <= len(options) <= 20:
                raise ValueError()
            ids.add(qid)
            option_ids = [option['id'] for option in options]
            if any(type(oid) is not int or not 1 <= oid <= MAX_ID for oid in option_ids) or len(set(option_ids)) != len(option_ids) or type(key) is not int or key not in option_ids:
                raise ValueError()
            # The old answers table has real question/option foreign keys. If
            # structural content was deleted, fail safely instead of grading
            # against a different quiz or losing saved selections.
            current = db.execute('SELECT id FROM quiz_questions WHERE id=? AND quiz_id=?', (qid, attempt['quiz_id'])).fetchone()
            existing = {row['id'] for row in db.execute('SELECT id FROM quiz_options WHERE question_id=?', (qid,))}
            if current is None or not set(option_ids) <= existing:
                raise ValueError()
        return questions
    except (ValueError, TypeError, KeyError):
        raise APIError(409, 'Quiz question data changed or is unavailable. Close this attempt and contact your instructor before retrying.')


def submit_attempt(db, user, attempt_id, data):
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    attempt = owned_attempt(db, user, attempt_id)
    if attempt['submitted_at'] is not None:
        result = get_result(db, user, attempt_id)
        result.update(already_submitted=True,
                      message='This attempt was already submitted. Your original result is saved.' if result['result'] else 'This attempt was submitted before scoring was available. Its answers are preserved, but it has no recorded score.')
        return result
    if attempt['quiz_status'] != 'published':
        raise APIError(409, 'This quiz is no longer published. Your attempt has not been submitted.')
    questions = _snapshot(db, attempt)
    if not isinstance(data, dict) or not isinstance(data.get('answers'), list):
        raise APIError(400, 'Answers must be provided as a list.')
    if len(data['answers']) > len(questions):
        raise APIError(400, 'Too many question answers.')
    known = {question['id']: question for question in questions}
    selected = {}
    for answer in data['answers']:
        if not isinstance(answer, dict):
            raise APIError(400, 'Each answer must be an object.')
        qid = answer.get('question_id'); oid = answer.get('option_id')
        if type(qid) is not int or not 1 <= qid <= MAX_ID or qid not in known or qid in selected:
            raise APIError(400, 'Invalid or duplicate question answer.')
        if oid is not None and (type(oid) is not int or not 1 <= oid <= MAX_ID or oid not in {option['id'] for option in known[qid]['options']}):
            raise APIError(400, 'Selected option does not belong to this question.')
        selected[qid] = oid
    answered = {qid: oid for qid, oid in selected.items() if oid is not None}
    score = sum(answered.get(question['id']) == question['correct_option_id'] for question in questions)
    if db.execute('SELECT 1 FROM quiz_attempt_answers WHERE attempt_id=? LIMIT 1', (attempt_id,)).fetchone():
        raise APIError(409, 'This attempt already has stored answer data. It has been preserved; contact your instructor.')
    db.executemany('INSERT INTO quiz_attempt_answers(attempt_id,question_id,option_id) VALUES(?,?,?)',
                   [(attempt_id, qid, oid) for qid, oid in answered.items()])
    timestamp = db.execute("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')").fetchone()[0]
    db.execute('INSERT INTO quiz_attempt_results(attempt_id,score,max_score,answered_count,submitted_at) VALUES(?,?,?,?,?)',
               (attempt_id, score, len(questions), len(answered), timestamp))
    db.execute('UPDATE quiz_attempts SET submitted_at=? WHERE id=?', (timestamp, attempt_id))
    saved = db.execute('SELECT * FROM quiz_attempts WHERE id=?', (attempt_id,)).fetchone()
    result = receipt(db, saved)
    result.update(already_submitted=False, message='Quiz submitted successfully. Your answers and score have been saved.')
    return result
