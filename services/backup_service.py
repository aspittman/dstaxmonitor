"""Portable full-workspace backups. SQLite's backup API provides a consistent snapshot."""
from contextlib import closing
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from flask import current_app

SOURCE_FILES = ['app.py', 'config.py', 'requirements.txt', 'README.md', '.gitignore', 'restore_backup.py']
SOURCE_FOLDERS = ['services', 'models', 'templates', 'static', 'tests']


def create_backup():
    """Return a temporary ZIP stream; caller closes it after the download finishes.

    Include all years and actual upload files, including orphan files. The archive
    is never written into exports, so later backups cannot include prior backups.
    """
    config = current_app.config
    root = Path(current_app.root_path)
    stream = tempfile.TemporaryFile(mode='w+b')
    manifest = {'format': 'dstaxmonitor-backup', 'version': 1,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'database': 'data/dstaxmonitor.sqlite3', 'files': {},
                'missing_documents': []}
    try:
        with tempfile.TemporaryDirectory(prefix='dstaxmonitor-snapshot-') as temporary:
            snapshot = Path(temporary) / 'snapshot.sqlite3'
            with closing(sqlite3.connect(str(config['DATABASE']))) as source:
                with closing(sqlite3.connect(str(snapshot))) as destination:
                    source.backup(destination)
                    if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('Database integrity check failed; backup not generated.')
                    if destination.execute('PRAGMA foreign_key_check').fetchall():
                        raise ValueError('Database contains invalid references; backup not generated.')
                    for record_id, name, path in destination.execute('SELECT id,name,local_path FROM documents'):
                        if not path or not (Path(config['UPLOAD_DIR']) / path).is_file():
                            manifest['missing_documents'].append({'id': record_id, 'name': name})
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                def add(path, name):
                    if path.is_symlink():
                        raise ValueError('Backup encountered a symbolic link; replace it with a regular local file.')
                    # Hash precisely the bytes stored in the archive, even if an export changes during backup.
                    digest = hashlib.sha256()
                    with path.open('rb') as source_file, archive.open(name, 'w') as target:
                        for chunk in iter(lambda: source_file.read(1024 * 1024), b''):
                            digest.update(chunk)
                            target.write(chunk)
                    manifest['files'][name] = digest.hexdigest()
                add(snapshot, manifest['database'])
                for folder, target_folder in [('DATA_DIR', 'data'), ('UPLOAD_DIR', 'uploads'), ('EXPORT_DIR', 'exports'), ('RULE_DIR', 'tax_rules')]:
                    base = Path(config[folder])
                    for path in sorted(base.rglob('*')):
                        if path.is_symlink():
                            raise ValueError('Backup encountered a symbolic link; replace it with a regular local file.')
                        if not path.is_file():
                            continue
                        if folder == 'DATA_DIR' and (path.resolve() == Path(config['DATABASE']).resolve() or str(path).startswith(str(config['DATABASE']) + '-')):
                            continue  # The live database and its journal/WAL are replaced by the snapshot.
                        add(path, target_folder + '/' + path.relative_to(base).as_posix())
                for name in SOURCE_FILES:
                    add(root / name, name)
                for folder in SOURCE_FOLDERS:
                    for path in sorted((root / folder).rglob('*')):
                        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                            add(path, path.relative_to(root).as_posix())
                archive.writestr('RESTORE.txt', RESTORE_TEXT)
                manifest['files']['RESTORE.txt'] = hashlib.sha256(RESTORE_TEXT.encode()).hexdigest()
                archive.writestr('backup_manifest.json', json.dumps(manifest, indent=2))
        stream.seek(0)
        return stream, 'DSTaxMonitor-backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.zip'
    except Exception:
        stream.close()
        raise


RESTORE_TEXT = '''DSTaxMonitor full backup — all tax years

Contains a consistent SQLite snapshot, uploaded documents, existing accountant
exports, tax rules, source code and local settings. No Google Drive connection
is required: upload this ZIP to your private Google Drive after downloading.
This ZIP is not encrypted and contains sensitive financial information.

Restore on Linux:
1. Install Python 3.10 or newer. Download this backup from Google Drive.
2. Obtain restore_backup.py from this ZIP (or your trusted DSTaxMonitor copy).
3. Run: python3 restore_backup.py /path/to/backup.zip --destination /path/to/new-empty-folder
   This verifies checksums and refuses to overwrite an existing workspace.
4. cd /path/to/new-empty-folder
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   python app.py
5. Open http://127.0.0.1:5000 and verify your records and Tax Vault documents.

The package includes all years regardless of the selected dashboard year.
backup_manifest.json lists any already-missing document evidence; a backup
cannot recreate documents that were missing when it was made. Checksums detect
accidental corruption; they do not authenticate an untrusted archive.
Restore creates a fresh session key and permissions and preserves the database
and document references. Keep the original ZIP until restoration is confirmed.
'''
