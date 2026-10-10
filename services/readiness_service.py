from .document_service import document_path
from .money import D, ZERO

def readiness(inputs,estimate):
    s=inputs['settings']; docs=inputs['documents']; transactions=inputs['transactions']
    available=[d for d in docs if document_path(d) is not None and d['status']=='Approved']
    receipts={d['transaction_id'] for d in available if d['category'] in ['Receipts','Expenses']}
    proofs={d['payment_id'] for d in available if d['category']=='Tax Payments'}
    missing=[t for t in transactions if t['type']=='Expense' and t['status']!='Excluded' and t['id'] not in receipts]
    review=[t for t in transactions if t['status'] in ['Possible','Needs Review']]
    uncategorized=[t for t in transactions if t['category']=='Uncategorized' and t['status']!='Excluded']
    categories={d['category'] for d in available}
    needed=[]
    if any(t.get('sale_date') and t['asset_type']!='Crypto' for t in inputs['trades']): needed.append('1099-B')
    if any('Dividend' in i['type'] for i in inputs['income']): needed.append('1099-DIV')
    if any(i['type']=='Interest' for i in inputs['income']): needed.append('1099-INT')
    needed+=['K-1','Partnership Documents']
    missing_docs=[c for c in needed if c not in categories]
    checks=[('Income reconciled',bool(s['income_reconciled'])),('Expenses reviewed',not review and not uncategorized),('Receipts complete',not missing),('Mileage complete / not applicable',bool(s['mileage_complete']) and all(m['status'] in ['Approved','Excluded'] for m in inputs['mileage'])),('Partner information complete',estimate['business']['allocation'] is not None),('Investments reconciled',bool(s['investments_reconciled']) and not estimate['investments']['issues']),('Required documents reviewed',not missing_docs),('K-1 information available',bool(s['k1_complete'])),('Payments complete and proof attached',bool(s['payments_complete']) and all(p['id'] in proofs for p in inputs['payments'])),('Tax rules and estimator scope ready',estimate['complete']),('Custom unresolved items complete',all(r['status'] in ['Approved','Excluded'] for r in inputs['review_items']))]
    return dict(percent=round(100*sum(v for _,v in checks)/len(checks)),checks=checks,missing_receipts=missing,review=review,uncategorized=uncategorized,missing_documents=missing_docs,missing_payment_proof=[p for p in inputs['payments'] if p['id'] not in proofs],possible=sum((D(t['amount']) for t in transactions if t['type']=='Expense' and t['status']=='Possible'),ZERO))
