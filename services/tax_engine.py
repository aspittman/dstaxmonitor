"""Pure deterministic estimation: normalized inputs in, trace and incomplete flags out.
Decimal throughout. Rules are supplied explicitly; no fallback year and no database access.
"""
import json
from .money import D, ZERO, money
from .business_service import business_summary
from .investment_service import investment_summary
from .state_tax_service import utah_estimate

def load_rules(directory,year):
    result = {}
    for jurisdiction in ['federal','utah']:
        path = directory / str(year) / (jurisdiction+'.json')
        try:
            rule = json.loads(path.read_text())
            if rule.get('tax_year') != year: raise ValueError('Tax year mismatch')
            result[jurisdiction] = rule
        except (OSError, ValueError): result[jurisdiction] = None
    return result

def brackets(amount, rules, offset=ZERO):
    total, trace, lower = ZERO, [], ZERO
    for bracket in rules:
        upper = D(bracket['up_to']) if bracket['up_to'] is not None else max(D(amount)+D(offset), lower)
        slice_ = max(ZERO, min(D(amount)+D(offset),upper)-max(D(offset),lower))
        tax = slice_*D(bracket['rate'])
        if slice_ > 0:
            trace.append(dict(lower=lower,upper=upper,rate=bracket['rate'],input=slice_,calculation=f'{slice_} × {bracket["rate"]}',result=tax))
        total += tax
        lower = upper
    return total,trace

def capital_netting(short,long,limit):
    net = D(short)+D(long)
    preferential = min(max(ZERO,D(long)),max(ZERO,net))
    ordinary = max(ZERO,net)-preferential if net>=0 else -min(-net,D(limit))
    return ordinary,preferential,max(ZERO,-net-D(limit))

def estimate(inputs,rules,hypothetical=ZERO):
    s=inputs['settings']; year=int(s['tax_year']); f=rules.get('federal'); u=rules.get('utah')
    f_ok=bool(f and f.get('verified') and f.get('tax_year')==year)
    u_ok=bool(u and u.get('verified') and u.get('tax_year')==year)
    b=business_summary(inputs['transactions'],inputs['mileage'],inputs['partners'],f if f_ok else None,hypothetical)
    inv=investment_summary(inputs['trades'],inputs['income'])
    issues=list(b['issues'])+inv['issues']; federal_issues=[]
    trace=[]
    def step(section,label,input_,rule,calculation,result,source_key=None,jurisdiction='federal'):
        r=f if jurisdiction=='federal' else u
        local=source_key=='local_records'
        trace.append(dict(section=section,label=label,input=input_,rule=rule,calculation=calculation,result=result,tax_year=year,version='bookkeeping-policy-v1' if local else (r or {}).get('version','Unavailable'),source='User-configured allocations and reviewed local records' if local else (r or {}).get('sources',{}).get(source_key,(r or {}).get('source_url','Unavailable')),last_verified='User review; approval date not tracked in V1' if local else (r or {}).get('last_verified','Unavailable')))
    step('Business','Estimated net profit',dict(revenue=b['revenue'],expenses=b['expenses'],mileage=b['mileage']),'Approved business records only','revenue − approved expenses − approved mileage',b['profit'],'local_records')
    step('Business','Estimated allocated share',dict(profit=b['profit'],allocation=b['allocation']),'Configured profit/loss allocation','profit × allocation / 100',b['share'],'local_records')
    for m in b['mileage_details']: step('Business','Mileage '+m['date'],m['input'],'Date-specific mileage rate',f"{m['input']} × {m['rate']}",m['result'],m['source_key'])
    step('Investments','Realized gains/losses',dict(short=inv['short'],long=inv['long']),'Approved realized lots; unrealized excluded','proceeds − total lot basis − sale fees',inv['net'],'capital_netting')
    step('Investments','Dividend and interest income',dict(ordinary_dividends=inv['dividends'],qualified_dividends=inv['qualified_dividends'],interest=inv['interest']),'Approved income records','ordinary + qualified dividends + taxable interest',inv['dividends']+inv['qualified_dividends']+inv['interest'],'capital_gains')
    if not f_ok: federal_issues.append('Federal rules unavailable or unverified for selected year.')
    status=s.get('filing_status')
    if f_ok and status not in f.get('ordinary_brackets',{}): federal_issues.append('Select a supported filing status.')
    if b['share'] is None: federal_issues.append('Partner allocation incomplete.')
    if b['share'] is not None and b['share']<0: federal_issues.append('Partnership loss needs basis, at-risk and passive-loss review; loss deduction not automatically allowed.')
    if not s.get('scope_reviewed'): federal_issues.append('Confirm estimator scope and accountant-reviewed QBI/adjustments in Settings.')
    if inv['issues']: federal_issues.extend(inv['issues'])
    if b['issues']: federal_issues.extend(b['issues'])
    if any(t['status'] not in ['Approved','Excluded'] for t in inputs['transactions'] if t['scope']=='Business'): federal_issues.append('Business transactions await review; calculations use approved records only.')
    ordinary_tax=cap_tax=se_tax=additional=agi=taxable=qbi=utah_gross=None
    half_se=ZERO
    if f_ok and status in f.get('ordinary_brackets',{}) and b['share'] is not None:
        share=max(ZERO,b['share']); se=f['se']; earnings=share*D(se['net_factor'])
        if s['se_mode']=='active':
            ss_base=min(earnings,max(ZERO,D(se['wage_base'])-D(s['ss_wages'])))
            se_tax=ss_base*D(se['ss_rate'])+earnings*D(se['medicare_rate']) if earnings>=D(se['minimum']) else ZERO
            half_se=se_tax*D(se['deductible_fraction'])
            step('Self-employment','Estimated regular SE tax',dict(allocated_share=share,net_earnings=earnings,ss_wages=s['ss_wages']),'Active partner assumption, regular method; SS wage cap',f'{ss_base} × {se["ss_rate"]} + {earnings} × {se["medicare_rate"]} (net earnings ≥ {se["minimum"]})',se_tax,'self_employment')
        elif s['se_mode']=='exempt':
            se_tax=ZERO
            step('Self-employment','SE tax assumption',share,'Accountant-confirmed exempt partner allocation','Configured exclusion from SE tax',ZERO,'self_employment')
        else: federal_issues.append('Partner self-employment treatment must be configured; LLC membership alone does not determine it.')
        wages=D(s['medicare_wages'])
        additional=(max(ZERO,wages-D(se['thresholds'][status]))+max(ZERO,(earnings if s['se_mode']=='active' else ZERO)-max(ZERO,D(se['thresholds'][status])-wages)))*D(se['additional_rate'])
        step('Self-employment','Additional Medicare tax',dict(medicare_wages=wages,net_earnings=earnings,threshold=se['thresholds'][status]),'Threshold depends on filing status','wages and eligible SE earnings above threshold × additional rate',additional,'additional_medicare')
        ordinary_gain,preferential,unused=capital_netting(inv['short'],inv['long'],f['capital_loss_limit'][status])
        step('Investments','Capital netting',dict(short=inv['short'],long=inv['long'],limit=f['capital_loss_limit'][status]),'Cross-net short/long; limit ordinary loss deduction','ordinary portion; preferential portion; unused loss (not an automatic carryforward)',dict(ordinary=ordinary_gain,preferential=preferential,unused_loss=unused),'capital_netting')
        preferred=preferential+inv['qualified_dividends']
        gross=share+D(s['other_income'])+inv['interest']+inv['dividends']+inv['qualified_dividends']+ordinary_gain+preferential
        agi=gross-D(s['adjustments'])-half_se
        deduction=D(f['standard_deduction'][status]); qbi=D(s['qbi_deduction'])
        taxable=max(ZERO,agi-deduction-qbi)
        ordinary_base=max(ZERO,taxable-preferred); preferred_base=taxable-ordinary_base
        step('Federal','Estimated AGI',dict(business_share=share,other_income=s['other_income'],investment_income=gross-share-D(s['other_income']),adjustments=s['adjustments'],half_se=half_se),'Reviewed income and adjustments','gross income − manual adjustments − deductible half SE tax',agi,'self_employment')
        step('Federal','Estimated taxable income',dict(agi=agi,standard_deduction=deduction,qbi=qbi),'Standard deduction; manually reviewed QBI amount','max(0, AGI − standard deduction − reviewed QBI)',taxable,'standard_deduction')
        ordinary_tax,bt=brackets(ordinary_base,f['ordinary_brackets'][status])
        for t in bt: step('Federal','Ordinary bracket',dict(lower=t['lower'],upper=t['upper'],taxable_slice=t['input']),f"Rate {t['rate']}",t['calculation'],t['result'],'brackets')
        cap_tax,ct=brackets(preferred_base,f['capital_gains'][status],ordinary_base)
        for t in ct: step('Federal','Preferential bracket',dict(ordinary_stack=ordinary_base,lower=t['lower'],upper=t['upper'],taxable_slice=t['input']),f"Rate {t['rate']}",t['calculation'],t['result'],'capital_gains')
        # Qualified dividend worksheet caps preferential result at ordinary tax on all taxable income.
        ordinary_cap,_=brackets(taxable,f['ordinary_brackets'][status])
        cap_tax=min(cap_tax,max(ZERO,ordinary_cap-ordinary_tax))
        step('Federal','Estimated federal income tax',dict(ordinary=ordinary_tax,capital=cap_tax),'Preferential worksheet ordinary-tax ceiling','ordinary + preferential, capped at ordinary tax on all taxable income',ordinary_tax+cap_tax,'capital_gains')
        if agi>D(se['thresholds'][status]): federal_issues.append('High-income review required: NIIT, AMT and other limitations are not modeled.')
        if qbi>max(ZERO,(taxable+qbi-preferred)*D(f['qbi_basic_ceiling_rate'])): federal_issues.append('Manual QBI exceeds basic taxable-income ceiling; accountant review required.')
        if u and u.get('tax_year')==year and u.get('rate_verified'):
            utah_gross=max(ZERO,agi)*D(u['rate'])
            step('Utah','Estimated gross Utah tax before credits',dict(federal_agi=agi,rate=u['rate']),'Full-year UT resident assumption; no state additions/subtractions','max(0, federal AGI) × verified rate; credits not included',utah_gross,'rate','utah')
    utah_tax=None
    if not u_ok: issues.append('Utah rules unverified/incomplete: final taxpayer credits and state adjustments unavailable. Final Utah tax and combined totals withheld.')
    elif agi is not None:
        utah_tax, state_trace, state_issues = utah_estimate(agi,D(f['standard_deduction'][status]),s,u)
        issues.extend(state_issues)
        for t in state_trace: step('Utah',t['label'],t['input'],t['rule'],t['calculation'],t['result'],t['source'],'utah')
    if s.get('state')!='UT': issues.append('Only Utah is supported; configure full-year Utah residency.')
    federal_issues=list(dict.fromkeys(federal_issues)); issues=list(dict.fromkeys(issues+federal_issues))
    federal_income=ordinary_tax+cap_tax if ordinary_tax is not None else None
    federal_total=federal_income+se_tax+additional if federal_income is not None and se_tax is not None and not federal_issues else None
    payments={k:sum((D(p['amount']) for p in inputs['payments'] if p['jurisdiction']==k),ZERO) for k in ['Federal','Utah','Other']}
    credited=payments['Federal']+payments['Utah']+D(s['federal_withholding'])+D(s['state_withholding'])
    federal_remaining=federal_total-payments['Federal']-D(s['federal_withholding']) if federal_total is not None else None
    step('Payments','Estimated remaining federal tax',dict(federal_estimate=federal_total,federal_payments=payments['Federal'],federal_withholding=s['federal_withholding']),'Federal component only; no Utah amount included','federal estimate − federal payments − federal withholding',federal_remaining,'local_records')
    step('Payments','Creditable payments and withholding',dict(**payments,federal_withholding=s['federal_withholding'],state_withholding=s['state_withholding']),'Other payments excluded from modeled federal/Utah balance','federal payments + Utah payments + federal/state withholding',credited,'local_records')
    balance=tax_balance(federal_total,utah_tax,credited,D(s['reserve']),bool(issues))
    total,remaining,surplus=balance['total'],balance['remaining'],balance['surplus']
    reserve=D(s['reserve'])
    step('Final','Estimated remaining tax',dict(total=total,payments=credited),'Do not combine incomplete tax components','estimated total − creditable payments',remaining,'local_records')
    return dict(year=year,business=b,investments=inv,ordinary_tax=ordinary_tax,capital_tax=cap_tax,se_tax=se_tax,additional_medicare=additional,federal_income=federal_income,federal_total=federal_total,federal_remaining=federal_remaining,utah_gross=utah_gross,utah_tax=utah_tax,total=total,payments=payments,credited_payments=credited,remaining=remaining,reserve=reserve,surplus=surplus,agi=agi,taxable=taxable,issues=issues,federal_issues=federal_issues,trace=trace,complete=not issues and total is not None)

def what_if(inputs,rules,expense):
    expense=D(expense)
    if expense<0: raise ValueError('Potential expense must be nonnegative')
    current=estimate(inputs,rules); scenario=estimate(inputs,rules,expense)
    def difference(key):
        return current[key]-scenario[key] if current[key] is not None and scenario[key] is not None else None
    return dict(expense=expense,current=current,hypothetical=scenario,difference=difference('total'),federal_difference=difference('federal_total'),income_tax_difference=difference('federal_income'))


def tax_balance(federal, state, payments, reserve, incomplete=False):
    """Signed remaining estimate: negative represents an estimated overpayment."""
    if incomplete or federal is None or state is None:
        return dict(total=None,remaining=None,surplus=None)
    total=D(federal)+D(state)
    remaining=total-D(payments)
    return dict(total=total,remaining=remaining,surplus=D(reserve)-remaining)
