"""DSTaxMonitor local application entry point."""
import csv, io, secrets, os, argparse
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, abort, flash, redirect, render_template, request, session, send_file, url_for
from config import Config
from models.database import get_db, init_db, close_db, ensure_year, rows
from services.money import D, numeric, money
from services.tax_engine import load_rules, estimate, what_if
from services.transaction_service import DEFINITIONS, STATUS, DOC_CATEGORIES, validate_record, save_record, IMPORT_ADAPTERS
from services.document_service import upload_document, document_path
from services.readiness_service import readiness
from services.export_service import export_package, csv_text
from services.demo_service import seed_demo
from services.backup_service import create_backup
from services.local_security import LOCAL_HOSTS, local_origin_matches
NAV=[('dashboard','Dashboard'),('business','Business'),('transactions','Transactions'),('investments','Investments'),('mileage','Mileage'),('tax_vault','Tax Vault'),('tax_estimate','Tax Estimate'),('tax_rules','Tax Rules'),('accountant_export','Accountant Export'),('settings','Settings')]
TABLE_PAGE={'transactions':'transactions','partners':'business','investment_transactions':'investments','investment_income':'investments','mileage_entries':'mileage','tax_payments':'tax_estimate','review_items':'transactions'}

def create_app(test_config=None):
    app=Flask(__name__); app.config.from_object(Config)
    if test_config: app.config.update(test_config)
    for name in ['DATA_DIR','UPLOAD_DIR','EXPORT_DIR']:
        path=Path(app.config[name]); path.mkdir(parents=True,exist_ok=True); path.chmod(0o700); app.config[name]=path
    key_path=app.config['DATA_DIR']/'session.key'
    if not app.config.get('SECRET_KEY'):
        if not key_path.exists():
            with key_path.open('x') as key: key.write(secrets.token_hex(32))
            key_path.chmod(0o600)
        app.config['SECRET_KEY']=key_path.read_text().strip()
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
        Path(app.config['DATABASE']).chmod(0o600)
    @app.before_request
    def local_only():
        # Host check prevents DNS rebinding; address check rejects external peers even if misbound.
        if request.remote_addr not in ['127.0.0.1','::1']:
            abort(403, description='DSTaxMonitor accepts connections only from this computer. Open http://127.0.0.1:5000 directly.')
        try: host=urlsplit('http://'+request.host).hostname
        except ValueError: abort(403, description='Invalid local server address.')
        if host not in LOCAL_HOSTS:
            abort(403, description='This server address is not allowed. Open http://127.0.0.1:5000 directly.')
        if request.method in ['POST','PUT','PATCH','DELETE']:
            origin=request.headers.get('Origin')
            # Privacy tools may send an opaque Origin ('null'). A valid session-bound
            # CSRF token remains mandatory, so hiding Origin cannot bypass protection.
            if origin and origin != 'null' and not local_origin_matches(origin, request.host_url):
                abort(403, description='The browser origin does not match this local server. Open http://127.0.0.1:5000 directly, reload Settings, and save again. A proxy, tunnel, or browser privacy setting may be changing the request origin.')
            token=session.get('csrf_token')
            if not token or not secrets.compare_digest(token,request.form.get('csrf_token','')): abort(400,description='Invalid request token. Reload the page.')
        session.setdefault('csrf_token',secrets.token_hex(32))
    @app.after_request
    def secure_headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'"
        return response
    @app.template_filter('usd')
    def usd(value): return 'Unavailable' if value is None else f'${money(value):,.2f}'
    @app.template_filter('decimal')
    def decimal(value): return '—' if value is None else f'{D(value):,.2f}'
    def active_year(): return get_db().execute('SELECT tax_year FROM app_preferences WHERE id=1').fetchone()['tax_year']
    def normalized():
        year=active_year(); s=dict(get_db().execute('SELECT * FROM settings WHERE tax_year=?',(year,)).fetchone())
        return dict(settings=s,transactions=rows('transactions',year),partners=rows('partners',year),trades=rows('investment_transactions',year),income=rows('investment_income',year),mileage=rows('mileage_entries',year),payments=rows('tax_payments',year),documents=rows('documents',year),review_items=rows('review_items',year))
    def context():
        inputs=normalized(); rules=load_rules(Path(app.config['RULE_DIR']),active_year())
        for jurisdiction,rule in rules.items():
            if rule: get_db().execute('INSERT OR REPLACE INTO tax_rule_versions VALUES(?,?,?,?,?,?)',(active_year(),jurisdiction,rule['version'],int(rule['verified']),rule['last_verified'],rule['source_url']))
        get_db().commit()
        e=estimate(inputs,rules); r=readiness(inputs,e)
        return dict(inputs=inputs,estimate=e,readiness=r,rules=rules)
    @app.context_processor
    def common(): return dict(nav=NAV,year=active_year(),csrf_token=session.get('csrf_token',''),statuses=STATUS,doc_categories=DOC_CATEGORIES,business_name=get_db().execute('SELECT name FROM businesses WHERE id=1').fetchone()['name'])
    @app.get('/')
    def dashboard(): return render_template('dashboard.html',page='dashboard',**context())
    @app.get('/business')
    def business(): return render_template('business.html',page='business',**context())
    @app.get('/transactions')
    def transactions():
        c=context(); records=c['inputs']['transactions']
        for key in ['scope','type','category','status']:
            if request.args.get(key): records=[t for t in records if t[key]==request.args[key]]
        receipt_ids={d['transaction_id'] for d in c['inputs']['documents'] if document_path(d)}
        if request.args.get('receipt')=='missing': records=[t for t in records if t['type']=='Expense' and t['id'] not in receipt_ids]
        if request.args.get('receipt')=='attached': records=[t for t in records if t['id'] in receipt_ids]
        if request.args.get('queue')=='review': records=[t for t in records if t['status'] in ['Possible','Needs Review']]
        return render_template('transactions.html',page='transactions',records=records,receipt_ids=receipt_ids,**c)
    @app.get('/investments')
    def investments(): return render_template('investments.html',page='investments',**context())
    @app.get('/mileage')
    def mileage(): return render_template('mileage.html',page='mileage',**context())
    @app.get('/tax-vault')
    def tax_vault(): return render_template('tax_vault.html',page='tax_vault',evidence={d['id']:bool(document_path(d)) for d in normalized()['documents']},**context())
    @app.post('/tax-vault/upload')
    def upload():
        try:
            file=request.files.get('file')
            if not file or not file.filename: raise ValueError('Select a document')
            upload_document(file,request.form,active_year()); flash('Document stored in protected Tax Vault.','success')
        except ValueError as error: flash(str(error),'error')
        return redirect(url_for('tax_vault'))
    @app.get('/documents/<int:record_id>')
    def download_document(record_id):
        row=get_db().execute('SELECT * FROM documents WHERE id=?',(record_id,)).fetchone()
        if row is None: abort(404)
        path=document_path(dict(row))
        if path is None: abort(404,description='Document metadata exists but evidence file is missing')
        return send_file(path,as_attachment=request.args.get('view')!='1',download_name=row['name']+path.suffix)
    @app.route('/documents/<int:record_id>/edit',methods=['GET','POST'])
    def edit_document(record_id):
        row=get_db().execute('SELECT * FROM documents WHERE id=? AND tax_year=?',(record_id,active_year())).fetchone()
        if row is None: abort(404)
        if request.method=='POST':
            if request.form.get('status') not in STATUS or request.form.get('category') not in DOC_CATEGORIES: abort(400)
            name=request.form.get('name','').strip(); notes=request.form.get('notes','')
            if not name or len(name)>200 or len(notes)>2000: abort(400)
            associations={}
            for key,table in [('transaction_id','transactions'),('investment_id','investment_transactions'),('payment_id','tax_payments')]:
                raw=request.form.get(key,'')
                if raw:
                    if not raw.isdigit() or not get_db().execute(f'SELECT 1 FROM {table} WHERE id=? AND tax_year=?',(int(raw),active_year())).fetchone(): abort(400)
                    associations[key]=int(raw)
                else: associations[key]=None
            get_db().execute('UPDATE documents SET name=?,notes=?,status=?,category=?,transaction_id=?,investment_id=?,payment_id=? WHERE id=?',(name,notes,request.form['status'],request.form['category'],*associations.values(),record_id));get_db().commit()
            flash('Document metadata updated.','success');return redirect(url_for('tax_vault'))
        return render_template('document_edit.html',page='tax_vault',record=dict(row),**context())
    @app.route('/tax-estimate',methods=['GET','POST'])
    def tax_estimate():
        c=context(); scenario=None
        if request.method=='POST':
            try: scenario=what_if(c['inputs'],c['rules'],numeric(request.form.get('expense','')))
            except ValueError as e: flash(str(e),'error')
        return render_template('tax_estimate.html',page='tax_estimate',scenario=scenario,**c)
    @app.get('/tax-rules')
    def tax_rules(): return render_template('tax_rules.html',page='tax_rules',**context())
    @app.route('/accountant-export',methods=['GET','POST'])
    def accountant_export():
        c=context()
        if request.method=='POST':
            archive=export_package(c['inputs'],c['estimate'],c['readiness'],c['rules'])
            return send_file(archive,as_attachment=True,download_name=f'DSTaxMonitor-{active_year()}-{archive.name}')
        return render_template('accountant_export.html',page='accountant_export',**c)
    @app.route('/records/<table>/new',methods=['GET','POST'])
    @app.route('/records/<table>/<int:record_id>/edit',methods=['GET','POST'])
    def record_form(table,record_id=None):
        if table not in DEFINITIONS: abort(404)
        existing=get_db().execute(f'SELECT * FROM {table} WHERE id=? AND tax_year=?',(record_id,active_year())).fetchone() if record_id else None
        if record_id and existing is None: abort(404)
        record=dict(existing) if existing else {}
        if request.method=='POST':
            try:
                record=validate_record(table,request.form,active_year()); save_record(table,record,record_id);get_db().commit();flash('Record saved.','success')
                return redirect(url_for(TABLE_PAGE[table]))
            except ValueError as e: flash(str(e),'error');record=dict(request.form)
        return render_template('record_form.html',page=TABLE_PAGE[table],table=table,fields=DEFINITIONS[table],record=record,record_id=record_id)
    @app.get('/csv/<table>/template')
    def csv_template(table):
        if table not in DEFINITIONS: abort(404)
        output=csv_text([], [f[0] for f in DEFINITIONS[table]])
        return app.response_class(output,mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename={table}-template.csv'})
    @app.post('/csv/<table>/import')
    def csv_import(table):
        if table not in ['transactions','investment_transactions','investment_income','mileage_entries']: abort(404)
        try:
            file=request.files.get('file')
            if not file or not file.filename.lower().endswith('.csv'): raise ValueError('Select a CSV file')
            adapter=IMPORT_ADAPTERS.get(request.form.get('adapter','generic'))
            if not adapter: raise ValueError('Unknown import adapter')
            records=adapter(file.read(),table,active_year())
            # Atomic validation and insert: no partial batches.
            with get_db():
                for record in records: save_record(table,record)
            flash(f'Imported {len(records)} records. Review before including in estimate. Reimporting creates additional records.','success')
        except ValueError as e: flash(str(e),'error')
        return redirect(url_for(TABLE_PAGE[table]))
    @app.post('/backup/download')
    def download_backup():
        try:
            stream, filename = create_backup()
        except (ValueError, OSError) as error:
            flash(str(error), 'error')
            return redirect(url_for('settings'))
        try:
            response = send_file(stream, mimetype='application/zip', as_attachment=True, download_name=filename)
            response.call_on_close(stream.close)
            return response
        except Exception:
            stream.close()
            raise

    @app.route('/settings',methods=['GET','POST'])
    def settings():
        if request.method=='POST':
            try:
                year=int(request.form.get('tax_year',''))
                if not 2000<=year<=2100: raise ValueError('Tax year out of range')
                # Changing year first loads that year; never copies financial settings from a prior year.
                if year!=active_year():
                    ensure_year(year);get_db().execute('UPDATE app_preferences SET tax_year=? WHERE id=1',(year,));get_db().commit()
                    flash('Tax year changed. Configure this year independently.','success');return redirect(url_for('settings'))
                status=request.form.get('filing_status',''); mode=request.form.get('se_mode','unknown')
                if status not in ['','single','married_joint','married_separate','head_household'] or mode not in ['unknown','active','exempt']: raise ValueError('Invalid setting')
                name=request.form.get('business_name','').strip()
                if not name or len(name)>200: raise ValueError('Business name required (maximum 200 characters)')
                if request.form.get('classification')!='partnership': raise ValueError('Version 1 supports partnership only')
                values={k:numeric(request.form.get(k,'0')) for k in ['reserve','other_income','federal_withholding','state_withholding','adjustments','qbi_deduction','ss_wages','medicare_wages','utah_additions','utah_subtractions','utah_exemptions']}
                if D(values['utah_exemptions'])!=int(D(values['utah_exemptions'])): raise ValueError('Utah qualifying exemptions must be an integer')
                values.update(filing_status=status,se_mode=mode,state='UT')
                for k in ['scope_reviewed','income_reconciled','investments_reconciled','mileage_complete','payments_complete','k1_complete']: values[k]=int(request.form.get(k)=='1')
                get_db().execute('UPDATE settings SET '+','.join(k+'=?' for k in values)+' WHERE tax_year=?',[*values.values(),year]);get_db().execute('UPDATE businesses SET name=? WHERE id=1',(name,));get_db().commit();flash('Settings saved for selected tax year.','success')
            except (ValueError,TypeError) as e: flash(str(e),'error')
            return redirect(url_for('settings'))
        return render_template('settings.html',page='settings',**context())
    @app.post('/demo/seed')
    def demo_seed():
        try: seed_demo(active_year());flash('DEMO DATA active in selected year.','success')
        except ValueError as e: flash(str(e),'error')
        return redirect(url_for('dashboard'))
    @app.errorhandler(413)
    def too_large(error): return render_template('error.html',message='Upload exceeds 16 MB limit.'),413
    @app.cli.command('init-db')
    def initialize(): init_db();print('Database initialized; existing records preserved.')
    @app.cli.command('seed-demo')
    def seed(): seed_demo(active_year());print('Demo data enabled.')
    return app

if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser(description='DSTaxMonitor — localhost only')
    parser.add_argument('--data-dir',type=Path,help='Separate private local workspace (for isolated demo or testing)')
    parser.add_argument('--demo',action='store_true',help='Seed synthetic data; requires an empty selected year')
    args=parser.parse_args()
    overrides={}
    if args.data_dir:
        workspace=args.data_dir.resolve()
        overrides=dict(DATA_DIR=workspace/'data',UPLOAD_DIR=workspace/'uploads',EXPORT_DIR=workspace/'exports',DATABASE=workspace/'data/dstaxmonitor.sqlite3')
    application=create_app(overrides)
    if args.demo:
        with application.app_context():
            year=get_db().execute('SELECT tax_year FROM app_preferences WHERE id=1').fetchone()['tax_year']
            if not get_db().execute('SELECT demo FROM settings WHERE tax_year=?',(year,)).fetchone()['demo']:
                seed_demo(year)
    application.run(host='127.0.0.1',port=5000,debug=False)
