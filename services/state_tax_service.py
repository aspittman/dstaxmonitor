"""Separate Utah module; only runs with verified complete year-specific credit rules.
The bundled 2026 rules intentionally do not enable this module. Future verified
rule files can provide credit parameters without changing federal calculations.
"""
from .money import D, ZERO

def utah_estimate(agi,deduction,settings,rule):
    if not rule.get('verified') or rule.get('tax_year')!=int(settings['tax_year']):
        return None,[],['Verified year-specific Utah rules unavailable.']
    credit_rule=rule.get('taxpayer_credit')
    if not credit_rule:
        return None,[],['Utah taxpayer credit parameters unavailable.']
    keys=['utah_additions','utah_subtractions','utah_exemptions']
    if any(settings.get(k) is None for k in keys):
        return None,[],['Configure Utah additions, subtractions and qualifying exemptions.']
    status=settings['filing_status']
    if status not in credit_rule.get('phaseout_thresholds',{}):
        return None,[],['Utah filing status credit threshold unavailable.']
    base=max(ZERO,D(agi)+D(settings['utah_additions'])-D(settings['utah_subtractions']))
    exemptions=D(settings['utah_exemptions'])*D(credit_rule['exemption_amount'])
    initial=(D(deduction)+exemptions)*D(credit_rule['deduction_factor'])
    reduction=max(ZERO,base-D(credit_rule['phaseout_thresholds'][status]))*D(credit_rule['phaseout_rate'])
    credit=max(ZERO,initial-reduction)
    gross=base*D(rule['rate'])
    tax=max(ZERO,gross-credit)
    trace=[dict(label='Utah taxable base',input=dict(agi=agi,additions=settings['utah_additions'],subtractions=settings['utah_subtractions']),rule='Reviewed Utah adjustments',calculation='max(0, AGI + additions − subtractions)',result=base,source='rate'),dict(label='Utah taxpayer credit',input=dict(deduction=deduction,exemptions=exemptions,initial_credit=initial,phaseout=reduction),rule='Verified deduction credit and phaseout',calculation='max(0, (deduction + exemption amount) × credit factor − phaseout)',result=credit,source='credits'),dict(label='Estimated Utah tax',input=dict(gross=gross,credit=credit),rule='Nonrefundable taxpayer credit',calculation='max(0, gross Utah tax − taxpayer credit)',result=tax,source='credits')]
    return tax,trace,[]
