"""Issue #6: role-specific dashboard data from the authenticated user's scope."""
from datetime import datetime, timezone
from .security import APIError, PERMISSIONS, require_permission

ROLE_DETAILS = {
    'student': {
        'title': 'A little progress, every day.',
        'description': 'Find your study groups and keep your learning connected.',
        'group_heading': 'Your study groups', 'tools_heading': 'Your learning tools',
        'nav': ['Overview', 'Study groups', 'Learning tools'],
    },
    'instructor': {
        'title': 'Make room for better learning.',
        'description': 'Keep your teaching groups organized and your resources within reach.',
        'group_heading': 'Your teaching groups', 'tools_heading': 'Teaching tools',
        'nav': ['Overview', 'Teaching groups', 'Teaching tools'],
    },
    'administrator': {
        'title': 'A clear view of your workspace.',
        'description': 'Understand account activity, group access and the learning community.',
        'group_heading': 'All study groups', 'tools_heading': 'Administration',
        'nav': ['Overview', 'All groups', 'Administration'],
    },
}
GROUP_SCOPE = """?='administrator' OR g.created_by=? OR EXISTS (
    SELECT 1 FROM memberships m WHERE m.group_id=g.id AND m.user_id=?)"""


def require_dashboard_role(user, requested_role):
    if requested_role not in ROLE_DETAILS:
        raise APIError(404, 'Dashboard not found.')
    if user['role'] != requested_role:
        raise APIError(403, 'This dashboard belongs to another role. Open your own dashboard.')


def build_dashboard(db, user, *, features=None):
    require_permission(user, 'dashboard')
    role = user['role']
    require_dashboard_role(user, role)
    details = ROLE_DETAILS[role]
    parameters = (role, user['id'], user['id'])
    groups = [dict(row) for row in db.execute(
        f'SELECT g.id,g.name,g.created_by FROM study_groups g WHERE {GROUP_SCOPE} ORDER BY g.name,g.id', parameters)]
    for group in groups:
        group['can_manage'] = role == 'administrator' or (role == 'instructor' and group['created_by'] == user['id'])
        group['relationship'] = 'Owner' if group['created_by'] == user['id'] else ('Administrator access' if role == 'administrator' else 'Member')
    if role == 'student':
        peers = db.execute(f'''WITH visible AS (
            SELECT g.id,g.created_by FROM study_groups g WHERE {GROUP_SCOPE})
            SELECT count(*) FROM users u WHERE u.is_active=1 AND u.id<>? AND (
                u.id IN (SELECT created_by FROM visible) OR EXISTS (
                    SELECT 1 FROM memberships m JOIN visible v ON v.id=m.group_id WHERE m.user_id=u.id))''',
            (*parameters, user['id'])).fetchone()[0]
        summary = {'groups': len(groups), 'study_partners': peers}
        stats = [{'label': 'Your study groups', 'value': len(groups)}, {'label': 'Active study partners', 'value': peers}]
    elif role == 'instructor':
        owned = sum(group['created_by'] == user['id'] for group in groups)
        summary = {'managed_groups': owned, 'shared_groups': len(groups) - owned}
        stats = [{'label': 'Groups you manage', 'value': owned}, {'label': 'Other groups you joined', 'value': len(groups) - owned}]
    else:
        active = db.execute('SELECT count(*) FROM users WHERE is_active=1').fetchone()[0]
        memberships = db.execute('SELECT count(*) FROM memberships').fetchone()[0]
        summary = {'active_users': active, 'groups': len(groups), 'memberships': memberships}
        stats = [{'label': 'Active accounts', 'value': active}, {'label': 'Study groups', 'value': len(groups)}, {'label': 'Group memberships', 'value': memberships}]
    folders_available = bool((features or {}).get('folders'))
    group_action = {'key': 'groups', 'label': details['group_heading'], 'description': 'See the groups available to your account.', 'available': True, 'href': '#study-groups'}
    folder_action = {'key': 'folders', 'label': 'Group folders', 'description': 'Organize and browse folders in your permitted study groups.', 'available': folders_available, 'href': '/access#folders-panel' if folders_available else None}
    materials_available = bool((features or {}).get('materials')) and 'materials.read' in PERMISSIONS[role]
    material_action = {'key': 'materials', 'label': 'Study materials', 'description': 'Read and download shared course resources.', 'available': materials_available, 'href': '/materials' if materials_available else None}
    upcoming = {
        'quiz_attempts': ('Available quizzes', 'Practice with quizzes published for your groups.'),
        'results': ('Your results', 'Review your quiz scores and progress.'),
        'quiz_creation': ('Create quizzes', 'Prepare questions and assessments for your students.'),
        'performance': ('Student performance', 'Review learning outcomes for your teaching groups.'),
        'user_management': ('Users and permissions', 'Manage accounts and their permitted actions.'),
    }
    keys = {'student': ['quiz_attempts', 'results'],
            'instructor': ['quiz_creation', 'performance'],
            'administrator': ['user_management']}[role]
    actions = [group_action, folder_action, material_action]
    actions.extend({'key': key, 'label': upcoming[key][0], 'description': upcoming[key][1], 'available': False, 'href': None} for key in keys)
    if role == 'administrator':
        actions.append({'key': 'access_checks', 'label': 'Access checks', 'description': 'Verify role and group access for this account.', 'available': True, 'href': '/access'})
    return {
        'user': {key: user[key] for key in ('id', 'name', 'email', 'role')},
        'role': role, 'title': details['title'], 'description': details['description'],
        'group_heading': details['group_heading'], 'tools_heading': details['tools_heading'],
        'navigation': [{'label': label, 'href': href} for label, href in zip(details['nav'], ['#overview', '#study-groups', '#tools'])],
        'permissions': list(PERMISSIONS[role]), 'summary': summary, 'stats': stats,
        'groups': groups, 'actions': actions,
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
