import csv, io, json, shutil, uuid, zipfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from flask import current_app
from .money import D
from .document_service import document_path

def json_safe(value):
    if isinstance(value,Decimal): return str(value)
    if isinstance(value,dict): return {k:json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [json_safe(v) for v in value]
    return value

def csv_text(records,fields=None):
    fields=fields or (list(records[0]) if records else ['No records'])
    output=io.StringIO(newline=''); writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore'); writer.writeheader()
    for record in records:
        safe={k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in record.items()}
        writer.writerow(safe)
    return output.getvalue()

def export_package(inputs,estimate,readiness,rules):
    year=estimate['year']; token=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:10]
    directory=current_app.config['EXPORT_DIR']/str(year)/token
    for folder in ['summary','transactions','investments','documents','rules']: (directory/folder).mkdir(parents=True,exist_ok=True)
    def write(path,value): (directory/path).write_text(value,encoding='utf-8')
    for name in ['transactions','mileage','payments','partners']:
        write('transactions/'+name+'.csv',csv_text(inputs[name]))
    for name in ['trades','income']: write('investments/'+name+'.csv',csv_text(inputs[name]))
    write('investments/gain_loss_summary.json',json.dumps(json_safe(estimate['investments']),indent=2))
    write('summary/tax_estimate.json',json.dumps(json_safe(estimate),indent=2))
    write('summary/calculation_breakdown.csv',csv_text([{**r,'input':json.dumps(json_safe(r['input'])),'result':json.dumps(json_safe(r['result']))} for r in estimate['trace']]))
    write('summary/business.json',json.dumps(json_safe(estimate['business']),indent=2))
    expenses=defaultdict(lambda:D(0))
    for t in inputs['transactions']:
        if t['scope']=='Business' and t['type']=='Expense' and t['status']=='Approved': expenses[t['category']]+=D(t['amount'])
    write('summary/expenses_by_category.csv',csv_text([dict(category=k,amount=v) for k,v in expenses.items()],['category','amount']))
    unresolved={'estimate_issues':estimate['issues'],'readiness':readiness,'custom_items':inputs['review_items']}
    write('summary/unresolved.json',json.dumps(json_safe(unresolved),indent=2))
    write('summary/settings.json',json.dumps(inputs['settings'],indent=2))
    write('rules/snapshot.json',json.dumps(rules,indent=2))
    index=[]
    for d in inputs['documents']:
        source=document_path(d); target=str(d['id'])+'-'+(source.name if source else 'missing')
        if source: shutil.copyfile(source,directory/'documents'/target)
        index.append({**d,'export_file':target if source else '', 'evidence_status':'Attached' if source else 'Missing evidence'})
    write('documents/index.csv',csv_text(index))
    write('README.txt',f'DSTaxMonitor accountant review package — tax year {year}\nGenerated {token} UTC. '+('DEMO DATA\n' if inputs['settings']['demo'] else '\n')+'Estimates are incomplete where indicated. Not a tax return; nothing filed. Approved is a user review status, not a legal conclusion. Sources and versioned rules included. Other payments are not applied to federal/Utah balances. Original documents are unchanged. CSV strings beginning with spreadsheet formula characters are prefixed with an apostrophe.\n')
    archive=directory.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(directory.rglob('*')):
            if path.is_file(): z.write(path,path.relative_to(directory))
    archive.chmod(0o600)
    return archive
