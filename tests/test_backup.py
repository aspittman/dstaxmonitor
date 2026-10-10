import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from app import create_app
from models.database import get_db, ensure_year
from restore_backup import restore_backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = dict(TESTING=True, SECRET_KEY='test-only', DATA_DIR=self.root/'data',
                           UPLOAD_DIR=self.root/'uploads', EXPORT_DIR=self.root/'exports',
                           DATABASE=self.root/'data/dstaxmonitor.sqlite3')
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.client.get('/settings')
        with self.client.session_transaction() as session:
            self.token = session['csrf_token']

    def tearDown(self):
        self.temp.cleanup()

    def download(self):
        response = self.client.post('/backup/download', data={'csrf_token':self.token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/zip')
        data = response.data
        self.assertIn('DSTaxMonitor-backup-', response.headers['Content-Disposition'])
        response.close()
        return data

    def test_complete_restore_preserves_all_years_and_document_links(self):
        self.client.post('/demo/seed',data={'csrf_token':self.token})
        with self.app.app_context():
            ensure_year(2027)
            get_db().execute("UPDATE settings SET reserve='4321' WHERE tax_year=2027")
            get_db().commit()
            transaction_id=get_db().execute('SELECT id FROM transactions LIMIT 1').fetchone()[0]
        pdf=b'%PDF-1.4\noriginal receipt\n%%EOF'
        self.client.post('/tax-vault/upload',data={'csrf_token':self.token,
            'file':(io.BytesIO(pdf),'receipt.pdf'),'name':'Receipt', 'category':'Receipts',
            'status':'Approved','transaction_id':str(transaction_id)})
        (self.root/'exports'/'existing.csv').write_text('accountant export')
        backup=self.root/'backup.zip'
        backup.write_bytes(self.download())
        destination=self.root/'restored'
        manifest=restore_backup(backup,destination)
        self.assertIn('app.py',manifest['files'])
        self.assertIn('tax_rules/2026/federal.json',manifest['files'])
        self.assertIn('exports/existing.csv',manifest['files'])
        self.assertEqual(len(manifest['missing_documents']),1)  # demo metadata only
        with sqlite3.connect(destination/'data/dstaxmonitor.sqlite3') as db:
            self.assertEqual(db.execute('SELECT reserve FROM settings WHERE tax_year=2027').fetchone()[0],'4321')
            self.assertEqual(db.execute('SELECT count(*) FROM transactions').fetchone()[0],4)
            record_id,link,path=db.execute("SELECT id,transaction_id,local_path FROM documents WHERE name='Receipt'").fetchone()
            self.assertEqual(link,transaction_id)
        self.assertEqual((destination/'uploads'/path).read_bytes(),pdf)
        restored_app=create_app({**self.config,'DATA_DIR':destination/'data',
            'UPLOAD_DIR':destination/'uploads','EXPORT_DIR':destination/'exports',
            'DATABASE':destination/'data/dstaxmonitor.sqlite3','RULE_DIR':destination/'tax_rules'})
        with restored_app.test_client() as restored_client:
            self.assertEqual(restored_client.get('/').status_code,200)
            response=restored_client.get(f'/documents/{record_id}')
            self.assertEqual(response.data,pdf)
            response.close()

    def test_snapshot_handles_wal_and_leaves_original_data_untouched(self):
        with self.app.app_context():
            db=get_db()
            db.execute('PRAGMA journal_mode=WAL')
            db.execute("UPDATE settings SET reserve='9876' WHERE tax_year=2026")
            db.commit()
            data=self.download()
            self.assertEqual(db.execute('SELECT reserve FROM settings').fetchone()[0],'9876')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertNotIn('data/dstaxmonitor.sqlite3-wal',archive.namelist())
            self.assertNotIn('data/dstaxmonitor.sqlite3-shm',archive.namelist())
            snapshot=self.root/'snapshot.sqlite3'
            snapshot.write_bytes(archive.read('data/dstaxmonitor.sqlite3'))
        with sqlite3.connect(snapshot) as db:
            self.assertEqual(db.execute('SELECT reserve FROM settings').fetchone()[0],'9876')
        self.assertEqual(list((self.root/'exports').iterdir()),[])

    def test_button_and_security(self):
        self.assertIn(b'Back Up Now',self.client.get('/settings').data)
        self.assertEqual(self.client.get('/backup/download').status_code,405)
        self.assertEqual(self.client.post('/backup/download').status_code,400)
        self.assertEqual(self.client.post('/backup/download',data={'csrf_token':self.token},headers={'Host':'evil.example'}).status_code,403)

    def test_corruption_is_rejected_before_restore_writes(self):
        data=self.download()
        damaged=self.root/'damaged.zip'
        with zipfile.ZipFile(io.BytesIO(data)) as original, zipfile.ZipFile(damaged,'w') as target:
            for name in original.namelist():
                target.writestr(name,b'damaged' if name=='app.py' else original.read(name))
        destination=self.root/'restored'
        with self.assertRaisesRegex(ValueError,'checksum'):
            restore_backup(damaged,destination)
        self.assertFalse(destination.exists())

    def test_restore_refuses_existing_workspace(self):
        backup=self.root/'backup.zip';backup.write_bytes(self.download())
        existing=self.root/'existing';existing.mkdir();(existing/'valuable.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError,'not be overwritten'):
            restore_backup(backup,existing)
        self.assertEqual((existing/'valuable.txt').read_text(),'keep')

    def test_unsafe_archive_paths_are_rejected(self):
        archive=self.root/'bad.zip'
        with zipfile.ZipFile(archive,'w') as target:
            target.writestr('../outside.txt','bad')
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            restore_backup(archive,self.root/'restored')
        self.assertFalse((self.root/'outside.txt').exists())


if __name__=='__main__':
    unittest.main()
