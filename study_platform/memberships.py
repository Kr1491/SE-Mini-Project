"""Group admission: open joins or owner-reviewed requests for restricted groups."""
from .security import APIError, group_access, current_account

SCHEMA = """
CREATE TABLE IF NOT EXISTS membership_requests (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES study_groups(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TEXT,
    CHECK((status='pending' AND reviewed_by IS NULL AND reviewed_at IS NULL)
       OR (status IN ('approved','rejected') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS membership_requests_pending
    ON membership_requests(group_id,user_id) WHERE status='pending';
"""


def join_group(db,user,group_id):
    if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
    account=current_account(db,user)
    if account['role']!='student':raise APIError(403,'Only students can join study groups.')
    group=db.execute('SELECT id,name,created_by,join_policy FROM study_groups WHERE id=?',(group_id,)).fetchone()
    if group is None:raise APIError(404,'Study group not found.')
    if db.execute('SELECT 1 FROM memberships WHERE group_id=? AND user_id=?',(group_id,account['id'])).fetchone():
        return 200,{'joined':True,'already_member':True,'group':dict(group)}
    if group['join_policy']=='open':
        db.execute('INSERT INTO memberships(group_id,user_id) VALUES(?,?)',(group_id,account['id']))
        return 201,{'joined':True,'already_member':False,'group':dict(group)}
    pending=db.execute("SELECT id FROM membership_requests WHERE group_id=? AND user_id=? AND status='pending'",(group_id,account['id'])).fetchone()
    request_id=pending['id'] if pending else db.execute('INSERT INTO membership_requests(group_id,user_id) VALUES(?,?)',(group_id,account['id'])).lastrowid
    return 202,{'joined':False,'already_member':False,'request_id':request_id,'group_id':group_id,'status':'pending',
        'message':'Your request is waiting for the group owner or an administrator to approve it.'}


def list_requests(db,user):
    account=current_account(db,user)
    if account['role']=='student':
        rows=db.execute('''SELECT r.id,r.group_id,r.status,r.requested_at,r.reviewed_at,
            CASE WHEN EXISTS(SELECT 1 FROM memberships m WHERE m.group_id=r.group_id AND m.user_id=r.user_id)
                 THEN g.name ELSE NULL END AS group_name
            FROM membership_requests r JOIN study_groups g ON g.id=r.group_id
            WHERE r.user_id=? ORDER BY r.id DESC LIMIT 50''',(account['id'],))
        return {'requests':[dict(row) for row in rows],'can_review':False}
    if account['role'] not in ('instructor','administrator'):
        raise APIError(403,'You cannot review membership requests.')
    rows=db.execute('''SELECT r.id,r.group_id,g.name AS group_name,r.status,r.requested_at,
        u.name AS student_name,u.email AS student_email FROM membership_requests r
        JOIN study_groups g ON g.id=r.group_id JOIN users u ON u.id=r.user_id
        WHERE r.status='pending' AND (?='administrator' OR g.created_by=?)
        ORDER BY r.id LIMIT 50''',(account['role'],account['id']))
    return {'requests':[dict(row) for row in rows],'can_review':True}


def review_request(db,user,request_id,data):
    if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
    account=current_account(db,user)
    if account['role'] not in ('instructor','administrator'):
        raise APIError(403,'Only group owners and administrators can review requests.')
    if not isinstance(data,dict) or set(data)!={'decision'} or data['decision'] not in ('approve','reject'):
        raise APIError(400,'Choose approve or reject.')
    row=db.execute('SELECT * FROM membership_requests WHERE id=?',(request_id,)).fetchone()
    if row is None:raise APIError(404,'Membership request not found.')
    group_access(db,account,row['group_id'],manage=True)
    status='approved' if data['decision']=='approve' else 'rejected'
    if row['status']!='pending':
        if row['status']!=status:raise APIError(409,'This request has already been reviewed. Refresh the list.')
        return {'status':row['status'],'already_reviewed':True}
    if status=='approved':
        student=db.execute('SELECT role,is_active FROM users WHERE id=?',(row['user_id'],)).fetchone()
        if student is None or not student['is_active'] or student['role']!='student':
            raise APIError(409,'This account is no longer an active Student. Reject the request or refresh.')
        db.execute('INSERT OR IGNORE INTO memberships(group_id,user_id) VALUES(?,?)',(row['group_id'],row['user_id']))
    db.execute("UPDATE membership_requests SET status=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?",(status,account['id'],request_id))
    return {'status':status,'already_reviewed':False}
