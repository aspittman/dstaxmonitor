from datetime import date
from .money import D, ZERO

def classify(trade):
    if not trade.get('sale_date'): return 'Unrealized position', None
    if trade.get('cost_basis') in (None,'') or trade.get('proceeds') in (None,''): return 'Missing cost basis/proceeds', None
    purchase, sale = date.fromisoformat(trade['purchase_date']), date.fromisoformat(trade['sale_date'])
    try: anniversary = purchase.replace(year=purchase.year+1)
    except ValueError: anniversary = purchase.replace(year=purchase.year+1,day=28)
    term = 'Long-term' if sale>anniversary else 'Short-term'
    return term, D(trade['proceeds'])-D(trade['cost_basis'])-D(trade.get('fees'))

def investment_summary(trades,income):
    out = {k:ZERO for k in ['short_gains','short_losses','long_gains','long_losses','dividends','qualified_dividends','interest']}
    out['issues'],out['trades'] = [],[]
    for t in trades:
        term,gain = classify(t)
        out['trades'].append(dict(t,holding_period=term,gain=gain))
        if term.startswith('Missing'): out['issues'].append('Investment #'+str(t['id'])+': missing cost basis/proceeds')
        if t.get('sale_date') and t['status'] not in ['Approved','Excluded']: out['issues'].append('Investment #'+str(t['id'])+' requires reconciliation')
        if gain is not None and t['status']=='Approved':
            key = ('long' if term=='Long-term' else 'short')+('_gains' if gain>=0 else '_losses')
            out[key] += gain
    for i in income:
        if i['status'] not in ['Approved','Excluded']: out['issues'].append('Investment income #'+str(i['id'])+' needs review')
        if i['status']!='Approved': continue
        out[{'Interest':'interest','Ordinary Dividend':'dividends','Qualified Dividend':'qualified_dividends'}[i['type']]] += D(i['amount'])
    out['short'] = out['short_gains']+out['short_losses']
    out['long'] = out['long_gains']+out['long_losses']
    out['net'] = out['short']+out['long']
    return out
