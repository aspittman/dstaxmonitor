"""Validated record definitions shared by forms and generic CSV adapters.
Adapters produce normalized records. Future broker adapters register in IMPORT_ADAPTERS.
"""
import csv, io
from datetime import date
from .money import numeric, D
from models.database import get_db
STATUS=['Approved','Possible','Needs Review','Excluded']
CATEGORIES=['Uncategorized','Advertising','Software & APIs','Hosting','Domains','Equipment','Office','Professional Services','Contractors','Travel','Mileage','Education','Bank/Payment Fees','Insurance','Other']
DOC_CATEGORIES=['Income','Expenses','Receipts','Mileage','Bank Statements','Tax Payments','Partnership Documents','1099-B','1099-DIV','1099-INT','K-1','Prior Returns','Investment Statements','Other']
# field: (label, kind, options/required); all stored fields have explicit definitions.
DEFINITIONS={
 'transactions': [('date','Date','date',True),('vendor','Vendor / customer','text',True),('description','Description','text',False),('amount','Amount','number',True),('type','Transaction type','select',['Income','Expense']),('scope','Scope','select',['Business','Personal']),('category','Category','select',CATEGORIES),('purpose','Business purpose','text',False),('status','Review status','select',STATUS),('notes','Notes','text',False)],
 'investment_transactions':[('symbol','Asset / symbol','text',True),('asset_type','Asset type','select',['Stock','ETF','Crypto']),('purchase_date','Purchase date','date',True),('sale_date','Sale date (blank = unrealized)','date',False),('quantity','Quantity','number',True),('cost_basis','Total lot cost basis including purchase fees','number',False),('proceeds','Total gross sale proceeds','number',False),('fees','Sale fees (not already in basis/proceeds)','number',True),('broker','Broker','text',False),('status','Review status','select',STATUS),('notes','Notes','text',False)],
 'investment_income':[('date','Date','date',True),('symbol','Symbol','text',False),('type','Income type','select',['Ordinary Dividend','Qualified Dividend','Interest']),('amount','Amount (qualified portion entered separately)','number',True),('broker','Broker','text',False),('status','Review status','select',STATUS),('notes','Notes','text',False)],
 'mileage_entries':[('date','Date','date',True),('start','Starting location','text',True),('destination','Destination','text',True),('purpose','Business purpose','text',True),('miles','Business miles','number',True),('source','Source','text',False),('status','Review status','select',STATUS),('notes','Notes','text',False)],
 'tax_payments':[('date','Date','date',True),('amount','Amount','number',True),('jurisdiction','Jurisdiction','select',['Federal','Utah','Other']),('payment_type','Payment type','select',['Estimated Payment','Withholding','Other']),('reference','Confirmation / reference','text',False),('notes','Notes','text',False)],
 'partners':[('name','Partner name','text',True),('ownership','Ownership %','number',True),('profit_allocation','Profit allocation %','number',True),('loss_allocation','Loss allocation %','number',True),('is_user','This is me','select',['0','1'])],
 'review_items':[('description','Unresolved item','text',True),('status','Status','select',STATUS)]}

def validate_record(table,form,year):
    if table not in DEFINITIONS: raise ValueError('Unsupported record type')
    record={}
    for key,label,kind,options in DEFINITIONS[table]:
        value=str(form.get(key,'')).strip()
        if kind=='select':
            if value not in options: raise ValueError(label+': choose a valid option')
        elif kind=='number':
            if not value and options: raise ValueError(label+' is required')
            value=numeric(value) if value else None
        elif kind=='date':
            if not value and options: raise ValueError(label+' is required')
            if value:
                parsed=date.fromisoformat(value)
                if key!='purchase_date' and parsed.year!=year: raise ValueError(label+' must match selected tax year')
            else: value=None
        else:
            if options and not value: raise ValueError(label+' is required')
            if len(value)>2000: raise ValueError(label+' is too long')
        record[key]=value
    record['tax_year']=year
    if table=='transactions':
        record['business_id']=1 if record['scope']=='Business' else None
        if record['scope']=='Personal' and record['status']=='Approved': pass # Bookkeeping only; personal expenses never reduce partnership income.
    if table=='partners':
        record['business_id']=1
        if any(D(record[k])>100 for k in ['ownership','profit_allocation','loss_allocation']): raise ValueError('Allocation percentages cannot exceed 100')
    if table=='investment_transactions':
        if record['sale_date'] and record['sale_date']<record['purchase_date']: raise ValueError('Sale date precedes purchase date')
        if D(record['quantity'])<=0: raise ValueError('Quantity must be positive')
        if record['status']=='Approved' and record['sale_date'] and (record['cost_basis'] is None or record['proceeds'] is None): raise ValueError('Approved realized trades require basis and proceeds')
    if table=='tax_payments' and record['payment_type']=='Other' and record['jurisdiction']!='Other': raise ValueError('Unclassified payments must use Other jurisdiction until reviewed')
    return record

def save_record(table,record,record_id=None):
    if table not in DEFINITIONS: raise ValueError('Unsupported table')
    db=get_db(); keys=list(record)
    if record_id:
        db.execute(f'UPDATE {table} SET '+','.join(k+'=?' for k in keys)+' WHERE id=? AND tax_year=?',[*record.values(),record_id,record['tax_year']])
    else:
        return db.execute(f'INSERT INTO {table} ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',list(record.values())).lastrowid

def generic_csv(data,table,year):
    try: text=data.decode('utf-8-sig')
    except UnicodeDecodeError: raise ValueError('CSV must be UTF-8')
    reader=csv.DictReader(io.StringIO(text))
    expected={f[0] for f in DEFINITIONS[table]}
    if reader.fieldnames is None or len(reader.fieldnames)!=len(set(reader.fieldnames)) or not expected.issubset(reader.fieldnames): raise ValueError('CSV must include template headers: '+', '.join(sorted(expected)))
    records=[]
    for line,row in enumerate(reader,2):
        if line>10002: raise ValueError('CSV limit: 10,000 rows')
        try: records.append(validate_record(table,row,year))
        except (ValueError,TypeError) as e: raise ValueError(f'Row {line}: {e}')
    if not records: raise ValueError('CSV contains no records')
    return records
IMPORT_ADAPTERS={'generic':generic_csv}
