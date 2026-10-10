import copy
import unittest
from pathlib import Path
from decimal import Decimal
from services.money import D, money
from services.business_service import business_summary
from services.investment_service import classify, investment_summary
from services.tax_engine import estimate, brackets, capital_netting, load_rules, what_if, tax_balance
from services.state_tax_service import utah_estimate
ROOT=Path(__file__).resolve().parents[1]

def fixtures():
    return dict(settings=dict(tax_year=2026,filing_status='single',state='UT',reserve='1000',other_income='20000',federal_withholding='100',state_withholding='50',adjustments='0',qbi_deduction='0',se_mode='active',ss_wages='0',medicare_wages='0',scope_reviewed=1,utah_additions='0',utah_subtractions='0',utah_exemptions='0'),transactions=[dict(id=1,scope='Business',type='Income',status='Approved',amount='50000'),dict(id=2,scope='Business',type='Expense',status='Approved',amount='10000')],partners=[dict(name='User',ownership='40',profit_allocation='40',loss_allocation='30',is_user=1),dict(name='Partner',ownership='60',profit_allocation='60',loss_allocation='70',is_user=0)],trades=[],income=[],mileage=[],payments=[])

def synthetic_utah(rules):
    # Artificial fixture, not an assertion of actual 2026 Utah credit law.
    rule=copy.deepcopy(rules['utah']);rule.update(verified=True,version='TEST-ONLY',taxpayer_credit=dict(exemption_amount='1000',deduction_factor='0.06',phaseout_rate='0.01',phaseout_thresholds={'single':'20000'}))
    return rule

class FinancialTests(unittest.TestCase):
    def setUp(self): self.inputs=fixtures();self.rules=load_rules(ROOT/'tax_rules',2026)
    def test_business_profit_and_partner_allocation(self):
        b=business_summary(self.inputs['transactions'],[],self.inputs['partners'],self.rules['federal'])
        self.assertEqual(b['profit'],D('40000'));self.assertEqual(b['share'],D('16000'))
    def test_excluded_possible_personal_and_unreviewed(self):
        for status in ['Possible','Needs Review','Excluded']:
            self.inputs['transactions'].append(dict(scope='Business',type='Expense',status=status,amount='900'))
        self.inputs['transactions'].append(dict(scope='Personal',type='Expense',status='Approved',amount='900'))
        self.inputs['transactions'].append(dict(scope='Business',type='Income',status='Excluded',amount='900'))
        b=business_summary(self.inputs['transactions'],[],self.inputs['partners'],self.rules['federal'])
        self.assertEqual(b['expenses'],D('10000'));self.assertEqual(b['revenue'],D('50000'))
    def test_loss_allocation_and_no_automatic_loss_deduction(self):
        self.inputs['transactions'][0]['amount']='0'
        e=estimate(self.inputs,self.rules);self.assertEqual(e['business']['share'],D('-3000'));self.assertIsNone(e['federal_total'])
        self.assertTrue(any('basis' in x for x in e['issues']))
    def test_missing_invalid_partner_config(self):
        self.inputs['partners'][1]['profit_allocation']='50'
        self.assertIsNone(estimate(self.inputs,self.rules)['business']['share'])
    def test_date_specific_mileage(self):
        self.inputs['mileage']=[dict(date='2026-06-30',status='Approved',miles='100'),dict(date='2026-07-01',status='Approved',miles='100'),dict(date='2026-08-01',status='Possible',miles='200')]
        b=estimate(self.inputs,self.rules)['business']
        self.assertEqual(b['mileage'],D('148.50'));self.assertEqual(b['miles'],D('200'));self.assertEqual(b['profit'],D('39851.50'))
    def test_holding_period_calendar_anniversary(self):
        trade=dict(purchase_date='2024-03-01',sale_date='2025-03-01',cost_basis='100',proceeds='140',fees='2')
        self.assertEqual(classify(trade),('Short-term',D('38')))
        trade['sale_date']='2025-03-02';self.assertEqual(classify(trade)[0],'Long-term')
        trade['purchase_date']='2024-02-29';trade['sale_date']='2025-02-28';self.assertEqual(classify(trade)[0],'Short-term')
        trade['sale_date']=None;self.assertEqual(classify(trade),('Unrealized position',None))
    def test_missing_basis_not_zero(self):
        trade=dict(id=1,purchase_date='2025-01-01',sale_date='2026-03-01',cost_basis=None,proceeds='10000',fees='0',status='Needs Review')
        self.inputs['trades']=[trade];e=estimate(self.inputs,self.rules)
        self.assertEqual(e['investments']['net'],D(0));self.assertIsNone(e['federal_total']);self.assertTrue(e['investments']['issues'])
    def test_capital_cross_netting_and_loss_limit(self):
        self.assertEqual(capital_netting('-2000','5000','3000'),(D(0),D(3000),D(0)))
        self.assertEqual(capital_netting('5000','-2000','3000'),(D(3000),D(0),D(0)))
        self.assertEqual(capital_netting('-5000','1000','3000'),(D(-3000),D(0),D(1000)))
        self.assertEqual(capital_netting('-5000','1000','1500'),(D(-1500),D(0),D(2500)))
    def test_capital_math_fees_and_unrealized(self):
        trades=[dict(id=1,purchase_date='2023-01-01',sale_date='2026-01-02',cost_basis='1000',proceeds='1500',fees='10',status='Approved'),dict(id=2,purchase_date='2026-01-01',sale_date=None,cost_basis='100',proceeds='9000',fees='0',status='Approved')]
        summary=investment_summary(trades,[]);self.assertEqual(summary['long_gains'],D(490));self.assertEqual(summary['net'],D(490))
    def test_federal_bracket_boundaries(self):
        rule=self.rules['federal']['ordinary_brackets']['single']
        for amount,expected in [('0','0'),('12400','1240'),('50400','5800'),('105700','17966'),('201775','41024'),('640600','192979.25')]:
            self.assertEqual(brackets(D(amount),rule)[0],D(expected))
    def test_preferential_stacking(self):
        total,trace=brackets(D('10000'),self.rules['federal']['capital_gains']['single'],D('45000'))
        self.assertEqual(total,D('832.50'));self.assertEqual(len(trace),2)
    def test_standard_deduction_consumes_preferred_income(self):
        self.inputs['transactions']=[];self.inputs['settings'].update(other_income='0',se_mode='exempt')
        self.inputs['income']=[dict(id=1,type='Qualified Dividend',amount='20000',status='Approved')]
        e=estimate(self.inputs,self.rules);self.assertEqual(e['taxable'],D('3900'));self.assertEqual(e['federal_income'],D(0))
    def test_se_regular_half_adjustment_and_wage_cap(self):
        e=estimate(self.inputs,self.rules)
        self.assertEqual(e['se_tax'],D('2260.728'));self.assertEqual(e['agi'],D('34869.636'))
        self.inputs['settings']['ss_wages']='184500'
        self.assertEqual(estimate(self.inputs,self.rules)['se_tax'],D('428.504'))
    def test_se_minimum(self):
        self.inputs['transactions'][0]['amount']='10500'
        self.assertEqual(estimate(self.inputs,self.rules)['se_tax'],D(0))
    def test_payments_and_other_exclusion(self):
        self.inputs['payments']=[dict(jurisdiction='Federal',amount='2000'),dict(jurisdiction='Utah',amount='300'),dict(jurisdiction='Other',amount='800')]
        e=estimate(self.inputs,self.rules);self.assertEqual(e['credited_payments'],D('2450'));self.assertEqual(e['payments']['Other'],D(800))
    def test_remaining_and_reserve_math(self):
        self.assertEqual(tax_balance('1000','200','300','1000'),dict(total=D(1200),remaining=D(900),surplus=D(100)))
        self.assertEqual(tax_balance('1000','200','1500','1000')['remaining'],D(-300))
        self.assertIsNone(tax_balance('1000',None,'300','1000')['remaining'])
    def test_complete_synthetic_state_module_totals(self):
        self.rules['utah']=synthetic_utah(self.rules)
        e=estimate(self.inputs,self.rules)
        self.assertTrue(e['complete']);self.assertEqual(e['remaining'],e['federal_total']+e['utah_tax']-D(150))
        self.assertTrue(any(t['label']=='Utah taxpayer credit' for t in e['trace']))
    def test_what_if_no_mutation_and_allocation(self):
        before=copy.deepcopy(self.inputs);self.rules['utah']=synthetic_utah(self.rules)
        result=what_if(self.inputs,self.rules,D('1000'))
        self.assertEqual(self.inputs,before);self.assertEqual(result['current']['business']['share']-result['hypothetical']['business']['share'],D('400'))
        self.assertGreater(result['difference'],0);self.assertLess(result['difference'],D(1000))
    def test_unverified_no_fabricated_totals(self):
        e=estimate(self.inputs,self.rules);self.assertIsNone(e['utah_tax']);self.assertIsNone(e['total']);self.assertIsNone(e['remaining']);self.assertIsNotNone(e['utah_gross'])
        self.rules['federal']['verified']=False;e=estimate(self.inputs,self.rules);self.assertIsNone(e['ordinary_tax']);self.assertIsNone(e['se_tax'])
    def test_no_previous_year_fallback_and_mismatched_rule(self):
        self.assertEqual(load_rules(ROOT/'tax_rules',2027),dict(federal=None,utah=None))
        self.inputs['settings']['tax_year']=2027
        self.assertIsNone(estimate(self.inputs,self.rules)['federal_total'])
    def test_trace_metadata_and_reproducibility(self):
        a=estimate(self.inputs,self.rules);b=estimate(self.inputs,self.rules);self.assertEqual(a,b)
        for t in a['trace']: self.assertTrue({'input','rule','calculation','result','tax_year','version','source','last_verified'}.issubset(t))
    def test_federal_remaining_excludes_utah_payments(self):
        self.inputs['payments']=[dict(jurisdiction='Federal',amount='2000'),dict(jurisdiction='Utah',amount='300')]
        e=estimate(self.inputs,self.rules)
        self.assertEqual(e['federal_remaining'],e['federal_total']-D('2100'))
        self.assertIsNone(e['remaining'])
    def test_unknown_se_treatment_blocks_federal_total(self):
        self.inputs['settings']['se_mode']='unknown'
        e=estimate(self.inputs,self.rules)
        self.assertIsNone(e['se_tax']);self.assertIsNone(e['federal_total'])
    def test_additional_medicare_and_high_income_warning(self):
        self.inputs['settings'].update(medicare_wages='210000',other_income='210000')
        e=estimate(self.inputs,self.rules)
        self.assertEqual(e['additional_medicare'],(D('10000')+D('14776'))*D('0.009'))
        self.assertIsNone(e['federal_total']);self.assertTrue(any('High-income' in x for x in e['issues']))
    def test_missing_mileage_rate_warns(self):
        self.inputs['mileage']=[dict(date='2026-07-01',status='Approved',miles='100')]
        self.rules['federal']['mileage']=[]
        e=estimate(self.inputs,self.rules)
        self.assertTrue(any('mileage rate unavailable' in x for x in e['issues']))
        self.assertIsNone(e['federal_total'])
    def test_money_rounding(self): self.assertEqual(money('1.005'),D('1.01'))

if __name__=='__main__': unittest.main()
