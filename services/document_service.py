import hashlib, uuid
from pathlib import Path
from flask import current_app
from models.database import get_db
from .transaction_service import DOC_CATEGORIES, STATUS
ALLOWED={'.pdf':b'%PDF-', '.png':b'\x89PNG\r\n\x1a\n', '.jpg':b'\xff\xd8\xff', '.jpeg':b'\xff\xd8\xff'}

def upload_document(file,form,year):
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ALLOWED: raise ValueError('Upload a PDF, PNG or JPEG document')
    data=file.read()
    if not data.startswith(ALLOWED[suffix]): raise ValueError('File content does not match the selected type')
    if len(data)>current_app.config['MAX_CONTENT_LENGTH']: raise ValueError('Document too large')
    category=form.get('category','Other'); status=form.get('status','Needs Review')
    if category not in DOC_CATEGORIES or status not in STATUS: raise ValueError('Invalid document category/status')
    name=form.get('name','').strip() or Path(file.filename).name
    if len(name)>200 or len(form.get('notes',''))>2000: raise ValueError('Document metadata too long')
    associations={}
    for key,table in [('transaction_id','transactions'),('investment_id','investment_transactions'),('payment_id','tax_payments')]:
        value=form.get(key)
        if value:
            try: value=int(value)
            except ValueError: raise ValueError('Invalid document association')
            if not get_db().execute(f'SELECT id FROM {table} WHERE id=? AND tax_year=?',(value,year)).fetchone(): raise ValueError('Associated record must belong to selected year')
        else: value=None
        associations[key]=value
    generated=uuid.uuid4().hex+suffix
    path=current_app.config['UPLOAD_DIR']/generated
    path.write_bytes(data); path.chmod(0o600)
    try:
        get_db().execute('INSERT INTO documents(name,document_type,tax_year,category,transaction_id,investment_id,payment_id,business_id,notes,status,local_path,sha256) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (name,suffix[1:].upper(),year,category,associations['transaction_id'],associations['investment_id'],associations['payment_id'],1 if form.get('business')=='1' else None,form.get('notes',''),status,generated,hashlib.sha256(data).hexdigest()))
        get_db().commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise

def document_path(document):
    if not document['local_path']: return None
    base=current_app.config['UPLOAD_DIR'].resolve()
    path=(base/document['local_path']).resolve()
    if path.parent!=base: raise ValueError('Invalid stored document path')
    return path if path.is_file() else None
