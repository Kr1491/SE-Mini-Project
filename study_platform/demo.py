"""Dedicated local fixtures; never select arbitrary existing database accounts."""

USERS = (
    (1, 'Demo Instructor', 'instructor@example.test', 'instructor', None, 1),
    (2, 'Demo Student', 'student@example.test', 'student', None, 1),
    (3, 'Demo Administrator', 'admin@example.test', 'administrator', None, 1),
    (4, 'Demo Non-member', 'outsider@example.test', 'student', None, 1),
)
GROUPS = ((1, 'Software Engineering', 1), (2, 'Database Systems', 1), (3, 'Private Research', 3))
MEMBERSHIPS = ((1, 2), (2, 2))
FIXTURE_ERROR = 'Demo mode requires its own empty or unchanged fixture database. Choose a fresh --database path.'


def validate_demo(db):
    marker = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='demo_fixture_state'").fetchone()
    if not marker or not db.execute('SELECT 1 FROM demo_fixture_state WHERE id=1 AND version=1').fetchone():
        raise ValueError(FIXTURE_ERROR)
    users = tuple(tuple(row) for row in db.execute('SELECT id,name,email,role,password_hash,is_active FROM users ORDER BY id'))
    groups = tuple(tuple(row) for row in db.execute('SELECT id,name,created_by FROM study_groups ORDER BY id'))
    memberships = tuple(tuple(row) for row in db.execute('SELECT group_id,user_id FROM memberships ORDER BY group_id,user_id'))
    if users != USERS or groups != GROUPS or memberships != MEMBERSHIPS:
        raise ValueError(FIXTURE_ERROR)


def seed(db):
    # Serialize the empty-database check and fixture insertion.
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    marker = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='demo_fixture_state'").fetchone()
    if marker:
        validate_demo(db)
        return
    for table in ('users', 'study_groups', 'memberships', 'sessions'):
        if db.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
            raise ValueError(FIXTURE_ERROR)
    db.executemany('INSERT INTO users(id,name,email,role,password_hash,is_active) VALUES(?,?,?,?,?,?)', USERS)
    db.executemany('INSERT INTO study_groups(id,name,created_by) VALUES(?,?,?)', GROUPS)
    db.executemany('INSERT INTO memberships(group_id,user_id) VALUES(?,?)', MEMBERSHIPS)
    db.execute('CREATE TABLE demo_fixture_state(id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)')
    db.execute('INSERT INTO demo_fixture_state VALUES(1,1)')
