# Database Backup and Recovery

## What is backed up?

Each backup contains:
- A consistent SQLite database snapshot.
- A copy of the uploaded materials directory.
- A manifest with SHA-256 checksums.

The database and uploaded files must be backed up together because database records refer to separately stored files.

## Creating a backup

Run from the project root:

    python3 -m study_platform.recovery backup --database var/issue5.db --storage var/materials --output .local-backups

For demo data, use:

    python3 -m study_platform.recovery backup --database var/demo-access.db --storage var/demo-materials --output .local-backups

The command prints the backup directory.

## Restoring a backup

1. Stop the application.
2. Identify the backup directory.
3. Run:

    python3 -m study_platform.recovery restore --backup-dir .local-backups/BACKUP_DIRECTORY --database var/issue5.db --storage var/materials

4. Restart the application.
5. Verify that users, groups, materials and uploaded files are accessible.

Use the matching demo database and storage paths when restoring demo data.

## Integrity verification

Before restoration, the module:
- Checks the backup format.
- Verifies database and uploaded-file SHA-256 checksums.
- Runs SQLite PRAGMA integrity_check.
- Runs SQLite PRAGMA foreign_key_check.

Invalid backups are rejected.

## Operational precautions

- Keep backups in a protected location.
- Never commit private backups or real user data to Git.
- Back up the database and uploaded files together.
- Stop the application before restoring.
- Keep multiple backup copies.
