from models.database import get_db
from .transaction_service import save_record, validate_record

def seed_demo(year):
    db=get_db()
    if any(db.execute(f'SELECT 1 FROM {t} WHERE tax_year=? LIMIT 1',(year,)).fetchone() for t in ['transactions','partners','investment_transactions','investment_income','mileage_entries','documents','tax_payments']): raise ValueError('Demo seeding requires an empty tax year; it never mixes with existing records')
    for name,user in [('Demo User','1'),('Demo Partner','0')]: save_record('partners',validate_record('partners',dict(name=name,ownership='50',profit_allocation='50',loss_allocation='50',is_user=user),year))
    for vendor,amount,type_,category,status in [('Demo Client','60000','Income','Other','Approved'),('Demo API','1200','Expense','Software & APIs','Approved'),('Demo Equipment','2000','Expense','Equipment','Possible'),('Demo Vendor','150','Expense','Uncategorized','Needs Review')]:
        save_record('transactions',validate_record('transactions',dict(date=f'{year}-03-01',vendor=vendor,description='Synthetic demo transaction',amount=amount,type=type_,scope='Business',category=category,purpose='Demo business activity',status=status,notes='DEMO'),year))
    save_record('mileage_entries',validate_record('mileage_entries',dict(date=f'{year}-08-01',start='Demo office',destination='Demo client',purpose='Client meeting',miles='120',source='Manual',status='Approved',notes='DEMO'),year))
    for purchase,sale,symbol,basis,proceeds in [(f'{year-2}-01-01',f'{year}-03-01','DEMO','3000','4500'),(f'{year}-01-01',f'{year}-04-01','LOSS','2000','1500'),(f'{year}-02-01','','HOLD','1000','')]:
        save_record('investment_transactions',validate_record('investment_transactions',dict(symbol=symbol,asset_type='ETF',purchase_date=purchase,sale_date=sale,quantity='10',cost_basis=basis,proceeds=proceeds,fees='5',broker='Demo Broker',status='Approved',notes='DEMO'),year))
    for type_,amount in [('Ordinary Dividend','250'),('Qualified Dividend','100'),('Interest','120')]: save_record('investment_income',validate_record('investment_income',dict(date=f'{year}-06-01',symbol='DEMO',type=type_,amount=amount,broker='Demo Broker',status='Approved',notes='DEMO'),year))
    save_record('tax_payments',validate_record('tax_payments',dict(date=f'{year}-06-15',amount='2000',jurisdiction='Federal',payment_type='Estimated Payment',reference='DEMO-ONLY',notes='Synthetic payment'),year))
    db.execute('INSERT INTO documents(name,document_type,tax_year,category,notes,status) VALUES(?,?,?,?,?,?)',('Demo receipt metadata (no evidence file)','PDF',year,'Receipts','Synthetic metadata, deliberately missing evidence','Needs Review'))
    db.execute("UPDATE settings SET filing_status='single',se_mode='active',reserve='5000',demo=1 WHERE tax_year=?",(year,))
    db.commit()
