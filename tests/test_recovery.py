import tempfile
import unittest
from pathlib import Path

from study_platform.db import connect, initialize
from study_platform.demo import seed
from study_platform.recovery import (
    create_backup,
    restore_backup,
    validate_backup,
)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / 'test.db'
        self.storage = self.root / 'uploads'
        self.backups = self.root / 'backups'

        initialize(self.database)
        with connect(self.database) as db:
            seed(db)

        self.storage.mkdir()
        (self.storage / 'sample.pdf').write_bytes(b'%PDF-1.4 sample')

    def tearDown(self):
        self.temp.cleanup()

    def test_backup_contains_database_and_uploaded_files(self):
        backup = create_backup(self.database, self.storage, self.backups)

        self.assertTrue((backup / 'database.sqlite3').is_file())
        self.assertTrue((backup / 'storage' / 'sample.pdf').is_file())
        self.assertTrue((backup / 'manifest.json').is_file())
        validate_backup(backup)

    def test_restore_recovers_database_and_uploaded_files(self):
        with connect(self.database) as db:
            original_name = db.execute(
                'SELECT name FROM users WHERE id = 1'
            ).fetchone()[0]

        backup = create_backup(self.database, self.storage, self.backups)

        with connect(self.database) as db:
            db.execute(
                "UPDATE users SET name = 'Changed' WHERE id = 1"
            )

        (self.storage / 'sample.pdf').unlink()
        (self.storage / 'new-file.txt').write_text('temporary')

        restore_backup(backup, self.database, self.storage)

        with connect(self.database) as db:
            count = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]

        self.assertGreater(count, 0)
        with connect(self.database) as db:
            restored_name = db.execute(
                'SELECT name FROM users WHERE id = 1'
            ).fetchone()[0]
        self.assertEqual(restored_name, original_name)

        self.assertEqual(
            (self.storage / 'sample.pdf').read_bytes(),
            b'%PDF-1.4 sample'
        )
        self.assertFalse((self.storage / 'new-file.txt').exists())

    def test_corrupted_database_backup_is_rejected(self):
        backup = create_backup(self.database, self.storage, self.backups)
        with (backup / 'database.sqlite3').open('ab') as damaged:
            damaged.write(b'corruption')

        with self.assertRaises(ValueError):
            validate_backup(backup)

    def test_corrupted_storage_backup_is_rejected(self):
        backup = create_backup(self.database, self.storage, self.backups)
        (backup / 'storage' / 'sample.pdf').write_bytes(b'corrupted')

        with self.assertRaises(ValueError):
            validate_backup(backup)


if __name__ == '__main__':
    unittest.main()
