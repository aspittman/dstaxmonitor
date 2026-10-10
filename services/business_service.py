from .money import D, ZERO

def business_summary(transactions, mileage, partners, rules, hypothetical=ZERO):
    included = [t for t in transactions if t['scope']=='Business' and t['status']=='Approved']
    revenue = sum((D(t['amount']) for t in included if t['type']=='Income'), ZERO)
    expenses = sum((D(t['amount']) for t in included if t['type']=='Expense'), ZERO) + D(hypothetical)
    deduction, miles, details, issues = ZERO, ZERO, [], []
    for entry in mileage:
        if entry['status'] != 'Approved': continue
        miles += D(entry['miles'])
        rate = next((r for r in (rules or {}).get('mileage',[]) if r['start']<=entry['date']<=r['end']), None) if (rules or {}).get('verified') else None
        if rate is None: issues.append('Verified mileage rate unavailable for '+entry['date']); continue
        amount = D(entry['miles'])*D(rate['rate'])
        deduction += amount
        details.append({'input':entry['miles'], 'date':entry['date'],'rate':rate['rate'],'result':amount,'source':rules['sources'][rate['source']],'source_key':rate['source']})
    profit = revenue - expenses - deduction
    valid = bool(partners) and all(sum((D(p[k]) for p in partners),ZERO)==100 for k in ['ownership','profit_allocation','loss_allocation']) and sum(bool(p['is_user']) for p in partners)==1
    user = next((p for p in partners if p['is_user']),None)
    allocation = D(user['profit_allocation' if profit >= 0 else 'loss_allocation']) if valid else None
    share = profit*allocation/100 if allocation is not None else None
    if not valid: issues.append('Partner ownership, profit and loss allocations must each total 100%; identify exactly one user partner.')
    return dict(revenue=revenue,expenses=expenses,mileage=deduction,miles=miles,profit=profit,allocation=allocation,share=share,mileage_details=details,issues=issues)
