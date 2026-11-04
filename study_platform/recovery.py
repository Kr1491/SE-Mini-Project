"""Backup and restore the study platform database and uploaded files."""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _private_directory(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('Backup and restore directories cannot be symbolic links.')
    if os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise PermissionError('Use an owned private directory with permissions 0700 for backups and restored data.')


def _private_tree(folder):
    for path in [Path(folder), *Path(folder).rglob('*')]:
        if path.is_symlink():
            raise ValueError('Symbolic links are not allowed.')
        if path.is_dir():
            path.chmod(0o700)
        elif path.is_file():
            path.chmod(0o600)
        else:
            raise ValueError('Only regular files and directories are allowed.')


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _check_database(path):
    with sqlite3.connect(str(path)) as db:
        result = db.execute('PRAGMA integrity_check').fetchone()[0]
        if result != 'ok':
            raise ValueError('Database integrity check failed.')
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Database contains foreign-key violations.')


def _file_manifest(folder):
    if Path(folder).is_symlink() or not Path(folder).is_dir():
        raise ValueError('Storage must be a real directory, not a symbolic link.')
    result = {}
    for path in sorted(Path(folder).rglob('*')):
        if path.is_symlink():
            raise ValueError('Symbolic links are not allowed.')
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = _sha256(path)
        elif not path.is_dir():
            raise ValueError('Only regular files and directories are allowed.')
    return result


def create_backup(database_path, storage_path, backup_root):
    database_path = Path(database_path)
    storage_path = Path(storage_path)
    backup_root = Path(backup_root)

    if database_path.is_symlink() or storage_path.is_symlink():
        raise ValueError('Backup source paths cannot be symbolic links.')
    if not database_path.is_file():
        raise FileNotFoundError('Database file does not exist.')

    _private_directory(backup_root)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    final_dir = backup_root / ('backup-' + timestamp)

    with tempfile.TemporaryDirectory(dir=backup_root) as temp:
        temp = Path(temp)
        snapshot = temp / 'database.sqlite3'
        storage_copy = temp / 'storage'
        storage_copy.mkdir(mode=0o700)

        with sqlite3.connect(str(database_path)) as source:
            with sqlite3.connect(str(snapshot)) as destination:
                source.backup(destination)

        snapshot.chmod(0o600)
        _check_database(snapshot)

        if storage_path.exists():
            if not storage_path.is_dir():
                raise ValueError('Storage path must be a directory.')
            _file_manifest(storage_path)
            # Preserve links during copying so validation rejects rather than
            # dereferences a link that appears while the source is copied.
            shutil.copytree(storage_path, storage_copy, dirs_exist_ok=True, symlinks=True)

        _private_tree(storage_copy)
        manifest = {
            'format_version': 1,
            'created_at': timestamp,
            'database_sha256': _sha256(snapshot),
            'storage_files': _file_manifest(storage_copy),
        }

        (temp / 'manifest.json').write_text(
            json.dumps(manifest, indent=2), encoding='utf-8'
        )
        (temp / 'manifest.json').chmod(0o600)
        os.replace(str(temp), str(final_dir))

    return final_dir


def validate_backup(backup_dir):
    backup_dir = Path(backup_dir)
    manifest_path = backup_dir / 'manifest.json'
    database = backup_dir / 'database.sqlite3'
    storage = backup_dir / 'storage'

    if any(path.is_symlink() for path in (backup_dir, manifest_path, database, storage)):
        raise ValueError('Backup components cannot be symbolic links.')
    if not manifest_path.is_file() or not database.is_file() or not storage.is_dir():
        raise ValueError('Backup is incomplete.')

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

    if manifest.get('format_version') != 1:
        raise ValueError('Unsupported backup format.')

    if _sha256(database) != manifest.get('database_sha256'):
        raise ValueError('Database checksum mismatch.')

    if _file_manifest(storage) != manifest.get('storage_files'):
        raise ValueError('Storage checksum mismatch.')

    _check_database(database)
    return manifest


def restore_backup(backup_dir, database_path, storage_path):
    backup_dir = Path(backup_dir)
    database_path = Path(database_path)
    storage_path = Path(storage_path)

    validate_backup(backup_dir)

    _private_directory(database_path.parent)
    _private_directory(storage_path.parent)

    if database_path.is_symlink() or storage_path.is_symlink():
        raise ValueError('Restore targets cannot be symbolic links.')
    if storage_path.exists():
        _file_manifest(storage_path)

    with tempfile.TemporaryDirectory(dir=database_path.parent) as db_temp:
        staged_db = Path(db_temp) / 'database.sqlite3'
        shutil.copy2(backup_dir / 'database.sqlite3', staged_db)
        staged_db.chmod(0o600)

        with tempfile.TemporaryDirectory(dir=storage_path.parent) as storage_temp:
            staged_storage = Path(storage_temp) / 'storage'
            shutil.copytree(backup_dir / 'storage', staged_storage, symlinks=True)
            _private_tree(staged_storage)

            _check_database(staged_db)

            old_db = Path(db_temp) / 'old-database.sqlite3'
            old_storage = Path(storage_temp) / 'old-storage'

            had_db = database_path.exists()
            had_storage = storage_path.exists()

            if had_db:
                shutil.copy2(database_path, old_db)
            if had_storage:
                shutil.copytree(storage_path, old_storage)

            try:
                os.replace(str(staged_db), str(database_path))

                if had_storage:
                    shutil.rmtree(storage_path)
                os.replace(str(staged_storage), str(storage_path))

            except Exception:
                if had_db and old_db.exists():
                    os.replace(str(old_db), str(database_path))
                elif database_path.exists():
                    database_path.unlink()

                if had_storage and old_storage.exists():
                    if storage_path.exists():
                        shutil.rmtree(storage_path)
                    os.replace(str(old_storage), str(storage_path))
                elif storage_path.exists():
                    shutil.rmtree(storage_path)
                raise


def main():
    parser = argparse.ArgumentParser(
        description='Back up or restore the study platform.'
    )
    commands = parser.add_subparsers(dest='action', required=True)

    backup = commands.add_parser('backup')
    backup.add_argument('--database', required=True)
    backup.add_argument('--storage', required=True)
    backup.add_argument('--output', default='.local-backups')

    restore = commands.add_parser('restore')
    restore.add_argument('--backup-dir', required=True)
    restore.add_argument('--database', required=True)
    restore.add_argument('--storage', required=True)

    args = parser.parse_args()

    if args.action == 'backup':
        result = create_backup(args.database, args.storage, args.output)
        print('Backup created:', result)
    else:
        restore_backup(args.backup_dir, args.database, args.storage)
        print('Backup restored successfully.')


if __name__ == '__main__':
    main()
