"""Restore a DSTaxMonitor ZIP into an empty directory, without third-party dependencies."""
import argparse
import hashlib
import json
import os
import sqlite3
import stat
import zipfile
from pathlib import Path, PurePosixPath


def restore_backup(archive_path, destination):
    destination = Path(destination).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Restore destination must be a new or empty directory. Existing data will not be overwritten.')
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate backup entries.')
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or not path.parts or path.as_posix() != entry.filename:
                raise ValueError('Unsafe backup path.')
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.is_dir():
                raise ValueError('Unsupported backup entry.')
        for name in names:
            if any(parent.as_posix() in names for parent in PurePosixPath(name).parents if parent.as_posix() != '.'):
                raise ValueError('Conflicting backup file paths.')
        manifest = json.loads(archive.read('backup_manifest.json'))
        if manifest.get('format') != 'dstaxmonitor-backup' or manifest.get('version') != 1:
            raise ValueError('Unsupported backup format.')
        if manifest.get('database') != 'data/dstaxmonitor.sqlite3':
            raise ValueError('Unsupported database location.')
        expected = manifest.get('files', {})
        if set(names) != set(expected) | {'backup_manifest.json'} or manifest['database'] not in expected:
            raise ValueError('Backup inventory does not match the manifest.')
        # Verify every file before creating the destination or writing any data.
        for name, checksum in expected.items():
            digest = hashlib.sha256()
            with archive.open(name) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != checksum:
                raise ValueError('Backup checksum failed: ' + name)
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.chmod(0o700)
        for name in names:
            target = destination.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with archive.open(name) as source, target.open('xb') as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    output.write(chunk)
            target.chmod(0o600)
    for folder in ['data', 'uploads', 'exports', 'tax_rules']:
        (destination / folder).mkdir(exist_ok=True, mode=0o700)
    # Invalidate backed-up sessions on the restored computer.
    (destination / 'data/session.key').unlink(missing_ok=True)
    with sqlite3.connect(str(destination / manifest['database'])) as database:
        if database.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or database.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Restored database failed integrity validation; keep your original backup.')
    return manifest


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = restore_backup(args.archive, args.destination)
    except (ValueError, OSError, zipfile.BadZipFile, KeyError) as error:
        parser.exit(1, 'Restore failed: ' + str(error) + '\n')
    print('Restored all tax years to', args.destination)
    print('Already-missing document files:', len(manifest['missing_documents']))
    print('See RESTORE.txt for startup instructions.')
