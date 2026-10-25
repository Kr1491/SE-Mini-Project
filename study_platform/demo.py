"""Explicit local test accounts/groups; not registration or group management."""


def seed(db):
    for row in [(1,'Demo Instructor','instructor@example.test','instructor'),
                (2,'Demo Student','student@example.test','student'),
                (3,'Demo Administrator','admin@example.test','administrator'),
                (4,'Demo Non-member','outsider@example.test','student')]:
        db.execute('INSERT OR IGNORE INTO users(id,name,email,role) VALUES(?,?,?,?)',row)
    for row in [(1,'Software Engineering',1),(2,'Database Systems',1),(3,'Private Research',3)]:
        db.execute('INSERT OR IGNORE INTO study_groups(id,name,created_by) VALUES(?,?,?)',row)
    for row in [(1,2),(2,2)]:
        db.execute('INSERT OR IGNORE INTO memberships VALUES(?,?)',row)
