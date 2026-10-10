import io
import csv
import tempfile
import unittest
import zipfile
from pathlib import Path
from app import create_app
from models.database import get_db, init_db
from services.transaction_service import DEFINITIONS
from services.export_service import csv_text

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.app=create_app(dict(TESTING=True,SECRET_KEY='test-key',DATA_DIR=self.root/'data',UPLOAD_DIR=self.root/'uploads',EXPORT_DIR=self.root/'exports',DATABASE=self.root/'data/app.sqlite3'))
        self.client=self.app.test_client();self.client.get('/')
        with self.client.session_transaction() as s: self.token=s['csrf_token']
    def tearDown(self): self.tmp.cleanup()
    def post(self,path,data=None): return self.client.post(path,data={**(data or {}),'csrf_token':self.token},follow_redirects=True)
    def seed(self): return self.post('/demo/seed')
    def test_database_init_idempotent_empty(self):
        with self.app.app_context():
            init_db();init_db();self.assertEqual(get_db().execute('SELECT count(*) FROM transactions').fetchone()[0],0)
            self.assertEqual(get_db().execute('PRAGMA foreign_keys').fetchone()[0],1)
            self.assertEqual(get_db().execute('SELECT count(*) FROM settings').fetchone()[0],1)
    def test_all_pages_empty_and_demo(self):
        paths=['/','/business','/transactions','/investments','/mileage','/tax-vault','/tax-estimate','/tax-rules','/accountant-export','/settings']
        for p in paths:self.assertEqual(self.client.get(p).status_code,200,p)
        self.seed()
        for p in paths:self.assertEqual(self.client.get(p).status_code,200,p)
        self.assertIn(b'DEMO DATA ACTIVE',self.client.get('/').data)
        for table in DEFINITIONS: self.assertEqual(self.client.get('/records/'+table+'/new').status_code,200)
    def test_localhost_host_peer_and_csrf_protection(self):
        self.assertEqual(self.client.get('/',headers={'Host':'attacker.example'}).status_code,403)
        self.assertEqual(self.client.get('/',environ_overrides={'REMOTE_ADDR':'192.168.1.2'}).status_code,403)
        self.assertEqual(self.client.post('/demo/seed').status_code,400)
        self.assertEqual(self.client.post('/demo/seed',data={'csrf_token':self.token},headers={'Origin':'https://attacker.example'}).status_code,403)
        r=self.client.get('/');self.assertEqual(r.headers['Cache-Control'],'no-store');self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])
    def test_upload_view_download_and_association(self):
        self.seed()
        with self.app.app_context():tid=get_db().execute("SELECT id FROM transactions WHERE type='Expense' LIMIT 1").fetchone()[0]
        r=self.post('/tax-vault/upload',dict(file=(io.BytesIO(b'%PDF-1.4\n%%EOF\n'),'../../receipt.pdf'),name='Test receipt',category='Receipts',status='Approved',transaction_id=str(tid)))
        self.assertEqual(r.status_code,200)
        with self.app.app_context():
            row=get_db().execute("SELECT * FROM documents WHERE name='Test receipt'").fetchone();rid=row['id'];self.assertEqual(row['transaction_id'],tid);self.assertNotIn('..',row['local_path']);self.assertTrue((self.root/'uploads'/row['local_path']).is_file())
        response=self.client.get(f'/documents/{rid}')
        self.assertEqual(response.data,b'%PDF-1.4\n%%EOF\n');response.close()
        response=self.client.get(f'/documents/{rid}?view=1')
        self.assertIn('inline',response.headers['Content-Disposition']);response.close()
        self.assertEqual(self.client.get('/static/receipt.pdf').status_code,404)
        r=self.post(f'/documents/{rid}/edit',dict(name='Renamed',category='Receipts',status='Needs Review',notes='review'))
        self.assertIn(b'Renamed',r.data)
    def test_reject_bad_upload_and_cross_year_association(self):
        for filename,data in [('evil.html',b'<script>'),('fake.pdf',b'<html>bad</html>')]:
            r=self.post('/tax-vault/upload',dict(file=(io.BytesIO(data),filename)));self.assertIn(b'alert error',r.data)
        self.assertEqual(list((self.root/'uploads').iterdir()),[])
        r=self.post('/tax-vault/upload',dict(file=(io.BytesIO(b'%PDF-1.4'),'ok.pdf'),transaction_id='999',category='Receipts',status='Approved'));self.assertIn(b'Associated record',r.data)
    def import_rows(self,table,records):
        fields=[f[0] for f in DEFINITIONS[table]];stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(records)
        return self.post('/csv/'+table+'/import',dict(file=(io.BytesIO(stream.getvalue().encode()),'input.csv')))
    def test_investment_and_mileage_csv_import(self):
        trade=dict(symbol='ABC',asset_type='Stock',purchase_date='2025-01-01',sale_date='2026-06-01',quantity='10',cost_basis='1000',proceeds='1500',fees='5',broker='Demo',status='Approved',notes='')
        self.assertIn(b'Imported 1',self.import_rows('investment_transactions',[trade]).data)
        mile=dict(date='2026-07-02',start='A',destination='B',purpose='Client',miles='100',source='CSV',status='Needs Review',notes='')
        self.assertIn(b'Imported 1',self.import_rows('mileage_entries',[mile]).data)
        income=dict(date='2026-06-01',symbol='ABC',type='Interest',amount='50',broker='Demo',status='Needs Review',notes='')
        self.assertIn(b'Imported 1',self.import_rows('investment_income',[income]).data)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT cost_basis FROM investment_transactions').fetchone()[0],'1000')
            self.assertEqual(get_db().execute('SELECT miles FROM mileage_entries').fetchone()[0],'100')
    def test_invalid_import_is_atomic_and_missing_basis_preserved(self):
        trade=dict(symbol='ABC',asset_type='Stock',purchase_date='2025-01-01',sale_date='2026-06-01',quantity='10',cost_basis='',proceeds='1500',fees='5',broker='Demo',status='Needs Review',notes='')
        bad={**trade,'quantity':'NaN'}
        self.assertIn(b'Row 3',self.import_rows('investment_transactions',[trade,bad]).data)
        with self.app.app_context():self.assertEqual(get_db().execute('SELECT count(*) FROM investment_transactions').fetchone()[0],0)
        self.import_rows('investment_transactions',[trade])
        with self.app.app_context():self.assertIsNone(get_db().execute('SELECT cost_basis FROM investment_transactions').fetchone()[0])
        self.assertIn(b'missing cost basis',self.client.get('/tax-estimate').data)
    def test_edit_transaction_and_filters(self):
        self.seed()
        with self.app.app_context(): t=dict(get_db().execute("SELECT * FROM transactions WHERE vendor='Demo Equipment'").fetchone())
        t['status']='Excluded';self.post(f"/records/transactions/{t['id']}/edit",t)
        self.assertIn(b'Demo Equipment',self.client.get('/transactions?status=Excluded').data)
        self.assertNotIn(b'Demo Equipment',self.client.get('/transactions?queue=review').data)
    def test_export_zip_contains_original_documents_trace_rules(self):
        self.seed();content=b'%PDF-1.4\nTEST DOCUMENT\n%%EOF'
        self.post('/tax-vault/upload',dict(file=(io.BytesIO(content),'test.pdf'),name='Supporting document',category='Receipts',status='Approved'))
        r=self.post('/accountant-export');self.assertEqual(r.status_code,200)
        with zipfile.ZipFile(io.BytesIO(r.data)) as archive:
            names=archive.namelist();self.assertIn('summary/calculation_breakdown.csv',names);self.assertIn('rules/snapshot.json',names);self.assertIn('documents/index.csv',names)
            pdf=next(n for n in names if n.endswith('.pdf'));self.assertEqual(archive.read(pdf),content)
            self.assertIn(b'Utah rules unverified',archive.read('summary/unresolved.json'));self.assertIn(b'DEMO DATA',archive.read('README.txt'))
        r.close()
        self.assertEqual(len(list((self.root/'uploads').iterdir())),1)
    def test_year_switch_and_no_fallback(self):
        self.seed();r=self.post('/settings',dict(tax_year='2027'))
        self.assertIn(b'2027',r.data);self.assertIn(b'No rule file for 2027',self.client.get('/tax-rules').data)
        self.assertNotIn(b'DEMO DATA ACTIVE',self.client.get('/').data)
        with self.app.app_context():self.assertEqual(get_db().execute('SELECT count(*) FROM partners WHERE tax_year=2027').fetchone()[0],0)
    def test_demo_never_mixes_existing_data(self):
        self.seed();self.assertIn(b'requires an empty tax year',self.seed().data)
        with self.app.app_context():self.assertEqual(get_db().execute('SELECT count(*) FROM transactions').fetchone()[0],4)
    def test_business_csv_and_numeric_validation(self):
        record=dict(date='2026-02-01',vendor='CSV Client',description='',amount='1000.10',type='Income',scope='Business',category='Other',purpose='',status='Approved',notes='')
        self.assertIn(b'Imported 1',self.import_rows('transactions',[record]).data)
        bad={**record,'amount':'-50'}
        self.assertIn(b'Number out of range',self.import_rows('transactions',[bad]).data)
        with self.app.app_context():
            self.assertEqual(get_db().execute('SELECT count(*) FROM transactions').fetchone()[0],1)
    def test_demo_document_metadata_does_not_count_as_evidence(self):
        self.seed()
        response=self.client.get('/tax-vault')
        self.assertIn(b'Missing evidence',response.data)
        response=self.client.get('/transactions?receipt=missing')
        self.assertIn(b'Demo API',response.data)
        self.assertEqual(self.client.get('/documents/1').status_code,404)
    def test_csv_formula_injection_protection(self):
        self.assertIn("'=HYPERLINK",csv_text([dict(v='=HYPERLINK("bad")')]))

if __name__=='__main__':unittest.main()
