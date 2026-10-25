"""Issue #12: group-authorized catalog and safe, bounded file streaming."""
import codecs
import os
import re
import stat
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, parse_qs
from .security import APIError, group_access, require_permission

CHUNK_SIZE = 64 * 1024
TEXT_EXTENSIONS = {'.txt', '.md', '.py', '.js', '.java', '.c', '.cpp', '.h', '.css', '.json', '.csv', '.xml', '.sql'}
IMAGE_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp'}
SCOPE = """?='administrator' OR g.created_by=? OR EXISTS (
    SELECT 1 FROM memberships member WHERE member.group_id=g.id AND member.user_id=?)"""


def integer(value, *, minimum=1, maximum=9223372036854775807, label='ID'):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+', value):
        raise APIError(400, f'Invalid {label}.')
    canonical = value.lstrip('0') or '0'
    if len(canonical) > len(str(maximum)):
        raise APIError(400, f'Invalid {label}.')
    result = int(canonical)
    if not minimum <= result <= maximum:
        raise APIError(400, f'Invalid {label}.')
    return result


def query_options(query):
    params = parse_qs(query, keep_blank_values=True, max_num_fields=20)
    result = {'group_id': None, 'limit': 24, 'offset': 0}
    for key in result:
        if key in params:
            if len(params[key]) != 1:
                raise APIError(400, f'Provide one {key}.')
            result[key] = integer(params[key][0], minimum=0 if key == 'offset' else 1,
                maximum=100 if key == 'limit' else 9223372036854775807, label=key)
    return result


def preview_kind(filename):
    suffix = Path(filename).suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return 'text'
    if suffix == '.pdf':
        return 'pdf'
    return 'image' if suffix in IMAGE_TYPES else None


def catalog(db, user, *, group_id=None, limit=24, offset=0):
    require_permission(user, 'materials.read')
    parameters = (user['role'], user['id'], user['id'])
    groups = [dict(row) for row in db.execute(f'SELECT g.id,g.name FROM study_groups g WHERE {SCOPE} ORDER BY g.name,g.id', parameters)]
    if group_id is not None:
        group_access(db, user, group_id)
    clause = f'({SCOPE})' + (' AND m.group_id=?' if group_id is not None else '')
    values = (*parameters, group_id) if group_id is not None else parameters
    total = db.execute(f'SELECT count(*) FROM materials m JOIN study_groups g ON g.id=m.group_id WHERE {clause}', values).fetchone()[0]
    rows = db.execute(f'''SELECT m.id,m.group_id,g.name AS group_name,m.title,m.original_name,
        m.size_bytes,m.created_at FROM materials m JOIN study_groups g ON g.id=m.group_id
        WHERE {clause} ORDER BY m.created_at DESC,m.id DESC LIMIT ? OFFSET ?''', (*values, limit, offset))
    items = []
    for row in rows:
        item = dict(row)
        item['preview_kind'] = preview_kind(item['original_name'])
        items.append(item)
    return {'groups': groups, 'materials': items, 'total': total, 'limit': limit, 'offset': offset, 'group_id': group_id}


def initialize_storage(storage):
    if os.open not in os.supports_dir_fd or not hasattr(os, 'O_NOFOLLOW'):
        raise RuntimeError('Secure material storage requires a POSIX server (macOS or Linux).')
    path = Path(storage)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError('Use a private, owned material directory with permissions 0700.')


@contextmanager
def storage_file(storage, key):
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,179}', key):
        raise APIError(404, 'The material file is unavailable.')
    directory = None
    descriptor = None
    stream = None
    try:
        directory = os.open(storage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise APIError(404, 'The material file is unavailable.')
        descriptor = os.open(key, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise APIError(404, 'The material file is unavailable.')
        stream = os.fdopen(descriptor, 'rb')
        descriptor = None
    except OSError as exc:
        raise APIError(404, 'The material file is unavailable.') from exc
    finally:
        if directory is not None:
            os.close(directory)
        if descriptor is not None:
            os.close(descriptor)
    try:
        yield stream, info.st_size
    finally:
        stream.close()


def safe_filename(name):
    leaf = unicodedata.normalize('NFC', name.replace('\\', '/').rsplit('/', 1)[-1])
    leaf = ''.join(c for c in leaf if not unicodedata.category(c).startswith('C')).strip()
    return leaf[:180] if leaf and leaf not in ('.', '..') else 'material'


def safe_content_type(filename, prefix):
    suffix = Path(filename).suffix.lower()
    if suffix == '.pdf' and prefix.startswith(b'%PDF-'):
        return 'application/pdf'
    if suffix == '.png' and prefix.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if suffix in ('.jpg', '.jpeg') and prefix.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if suffix == '.gif' and prefix[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if suffix == '.webp' and prefix.startswith(b'RIFF') and prefix[8:12] == b'WEBP':
        return 'image/webp'
    if suffix in TEXT_EXTENSIONS and b'\x00' not in prefix:
        try:
            codecs.getincrementaldecoder('utf-8')().decode(prefix, final=False)
            return 'text/plain; charset=utf-8'
        except UnicodeDecodeError:
            pass
    return 'application/octet-stream'


@dataclass
class MaterialFile:
    stream: object
    size: int
    content_type: str
    disposition: str


@contextmanager
def open_material(db, user, material_id, storage, download=False):
    require_permission(user, 'materials.read')
    row = db.execute('SELECT * FROM materials WHERE id=?', (material_id,)).fetchone()
    if row is None:
        raise APIError(404, 'Material not found.')
    group_access(db, user, row['group_id'])
    with storage_file(storage, row['stored_name']) as (stream, size):
        if size != row['size_bytes']:
            raise APIError(404, 'The material file is unavailable or incomplete.')
        content_type = safe_content_type(row['original_name'], stream.read(4096))
        stream.seek(0)
        mode = 'attachment' if download or content_type == 'application/octet-stream' else 'inline'
        filename = quote(safe_filename(row['original_name']), safe='')
        yield MaterialFile(stream, size, content_type, f"{mode}; filename*=UTF-8''{filename}")


class UnsatisfiableRange(Exception):
    pass


def _bounded_number(text, cap):
    canonical = text.lstrip('0') or '0'
    return cap + 1 if len(canonical) > len(str(cap)) else min(int(canonical), cap + 1)


def byte_range(header, size):
    # Ignore unknown/malformed units and multipart ranges; this server supports
    # single-byte ranges and full transfers, not multipart/byteranges.
    if not header:
        return None
    match = re.fullmatch(r'bytes=([0-9]*)-([0-9]*)', header.strip(), re.IGNORECASE)
    if not match or not any(match.groups()):
        return None
    if size == 0:
        raise UnsatisfiableRange()
    first, last = match.groups()
    if not first:
        count = _bounded_number(last, size)
        if count == 0:
            raise UnsatisfiableRange()
        return max(0, size - count), size - 1
    start = _bounded_number(first, size)
    end = min(_bounded_number(last, size), size - 1) if last else size - 1
    if start >= size or end < start:
        raise UnsatisfiableRange()
    return start, end
