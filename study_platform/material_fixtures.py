"""Small local demo files, never the real upload implementation."""
import io
import os
import zipfile
from .materials import storage_file
from .security import APIError


def sample_pdf():
    stream = b'BT /F1 22 Tf 70 750 Td (StudySpace - Sprint planning guide) Tj 0 -40 Td /F1 12 Tf (Plan, build, review and verify your working product.) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    data = bytearray(b'%PDF-1.4\n'); offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data)); data.extend(f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(data)
    data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        data.extend(f'{offset:010d} 00000 n \n'.encode())
    data.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(data)


def sample_png():
    return bytes.fromhex('89504e470d0a1a0a0000000d49484452000000080000000808020000004b6d29dc0000001149444154789c6310cf4fc48a18869604007e9239c1417b6ad10000000049454e44ae426082')


def sample_docx():
    output = io.BytesIO()
    files = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>StudySpace sample database handout.</w:t></w:r></w:p></w:body></w:document>',
    }
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as archive:
        for name, content in files.items():
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_STORED; info.create_system = 0
            archive.writestr(info, content)
    return output.getvalue()


def fixtures():
    return [
        (1, 'Sprint planning guide', 'sprint-guide.pdf', 'demo12-guide.pdf', 'application/pdf', sample_pdf(), 1),
        (1, 'Sample color swatch', 'sample-swatch.png', 'demo12-image.png', 'image/png', sample_png(), 1),
        (2, 'Access policy example', 'access_policy.py', 'demo12-policy.py', 'text/plain', b'# Group access example\ndef may_read(is_member, is_admin):\n    return is_member or is_admin\n', 1),
        (2, 'Database handout', 'database-handout.docx', 'demo12-handout.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', sample_docx(), 1),
        (3, 'Private research notes', 'private-notes.txt', 'demo12-private.txt', 'text/plain', b'RESTRICTED SAMPLE RESOURCE\nOnly authorized members or administrators may read this file.\n', 3),
    ]


def seed_materials(db, storage):
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    for group, title, name, key, mime, content, uploader in fixtures():
        expected = (group, title, name, key, mime, len(content), uploader)
        row = db.execute('''SELECT group_id,title,original_name,stored_name,content_type,size_bytes,uploaded_by
            FROM materials WHERE stored_name=?''', (key,)).fetchone()
        if row is not None and tuple(row) != expected:
            raise ValueError('A sample material conflicts with existing data. Choose a fresh demo database/storage path.')
        try:
            with storage_file(storage, key) as (stream, size):
                if size != len(content) or stream.read() != content:
                    raise ValueError('A sample file conflicts with existing data. Choose fresh demo storage.')
        except APIError:
            # Create exclusively; never overwrite an existing file or symlink.
            directory = os.open(storage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                descriptor = os.open(key, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(content)
            finally:
                os.close(directory)
        if row is None:
            db.execute('''INSERT INTO materials(group_id,title,original_name,stored_name,content_type,size_bytes,uploaded_by)
                VALUES(?,?,?,?,?,?,?)''', expected)
