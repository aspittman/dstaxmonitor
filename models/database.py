"""SQLite schema version 1. Monetary values stored as decimal text (never binary floats)."""
import sqlite3
from flask import current_app, g
SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS settings(tax_year INTEGER PRIMARY KEY, filing_status TEXT DEFAULT '', state TEXT DEFAULT 'UT', reserve TEXT DEFAULT '0', other_income TEXT DEFAULT '0', federal_withholding TEXT DEFAULT '0', state_withholding TEXT DEFAULT '0', adjustments TEXT DEFAULT '0', qbi_deduction TEXT DEFAULT '0', se_mode TEXT DEFAULT 'unknown', ss_wages TEXT DEFAULT '0', medicare_wages TEXT DEFAULT '0', scope_reviewed INTEGER DEFAULT 0, income_reconciled INTEGER DEFAULT 0, investments_reconciled INTEGER DEFAULT 0, mileage_complete INTEGER DEFAULT 0, payments_complete INTEGER DEFAULT 0, k1_complete INTEGER DEFAULT 0, utah_additions TEXT DEFAULT '0', utah_subtractions TEXT DEFAULT '0', utah_exemptions TEXT DEFAULT '0', demo INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS app_preferences(id INTEGER PRIMARY KEY CHECK(id=1), tax_year INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY, name TEXT NOT NULL, classification TEXT DEFAULT 'partnership');
CREATE TABLE IF NOT EXISTS partners(id INTEGER PRIMARY KEY, business_id INTEGER REFERENCES businesses(id), tax_year INTEGER NOT NULL, name TEXT NOT NULL, ownership TEXT NOT NULL, profit_allocation TEXT NOT NULL, loss_allocation TEXT NOT NULL, is_user INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY, business_id INTEGER REFERENCES businesses(id), date TEXT NOT NULL, vendor TEXT NOT NULL, description TEXT DEFAULT '', amount TEXT NOT NULL, type TEXT NOT NULL CHECK(type IN ('Income','Expense')), scope TEXT NOT NULL CHECK(scope IN ('Business','Personal')), category TEXT DEFAULT 'Uncategorized', purpose TEXT DEFAULT '', tax_year INTEGER NOT NULL, notes TEXT DEFAULT '', status TEXT NOT NULL CHECK(status IN ('Approved','Possible','Needs Review','Excluded')));
CREATE TABLE IF NOT EXISTS investment_transactions(id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, asset_type TEXT NOT NULL, purchase_date TEXT NOT NULL, sale_date TEXT, quantity TEXT NOT NULL, cost_basis TEXT, proceeds TEXT, fees TEXT DEFAULT '0', broker TEXT DEFAULT '', notes TEXT DEFAULT '', status TEXT DEFAULT 'Needs Review', tax_year INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS investment_income(id INTEGER PRIMARY KEY, date TEXT NOT NULL, symbol TEXT DEFAULT '', type TEXT NOT NULL, amount TEXT NOT NULL, broker TEXT DEFAULT '', notes TEXT DEFAULT '', status TEXT DEFAULT 'Needs Review', tax_year INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mileage_entries(id INTEGER PRIMARY KEY, date TEXT NOT NULL, start TEXT NOT NULL, destination TEXT NOT NULL, purpose TEXT NOT NULL, miles TEXT NOT NULL, source TEXT DEFAULT 'Manual', notes TEXT DEFAULT '', status TEXT DEFAULT 'Needs Review', tax_year INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS tax_payments(id INTEGER PRIMARY KEY, date TEXT NOT NULL, amount TEXT NOT NULL, jurisdiction TEXT NOT NULL, payment_type TEXT NOT NULL, reference TEXT DEFAULT '', notes TEXT DEFAULT '', tax_year INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, name TEXT NOT NULL, document_type TEXT NOT NULL, tax_year INTEGER NOT NULL, category TEXT NOT NULL, transaction_id INTEGER REFERENCES transactions(id), investment_id INTEGER REFERENCES investment_transactions(id), payment_id INTEGER REFERENCES tax_payments(id), business_id INTEGER REFERENCES businesses(id), uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP, notes TEXT DEFAULT '', status TEXT DEFAULT 'Needs Review', local_path TEXT UNIQUE, sha256 TEXT);
CREATE TABLE IF NOT EXISTS tax_rule_versions(tax_year INTEGER NOT NULL, jurisdiction TEXT NOT NULL, version TEXT NOT NULL, verified INTEGER NOT NULL, last_verified TEXT, source_url TEXT, PRIMARY KEY(tax_year,jurisdiction));
CREATE TABLE IF NOT EXISTS review_items(id INTEGER PRIMARY KEY, tax_year INTEGER NOT NULL, description TEXT NOT NULL, status TEXT DEFAULT 'Needs Review');
CREATE INDEX IF NOT EXISTS transactions_year ON transactions(tax_year);
CREATE INDEX IF NOT EXISTS documents_year ON documents(tax_year);
INSERT OR IGNORE INTO schema_migrations(version) VALUES(1);
INSERT OR IGNORE INTO businesses(id,name) VALUES(1,'DevSpace Technologies LLC');
"""
def connect(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn
def get_db():
    if 'db' not in g: g.db = connect(current_app.config['DATABASE'])
    return g.db
def init_db(year=2026):
    db = get_db()
    db.executescript(SCHEMA)
    existing_columns={row['name'] for row in db.execute('PRAGMA table_info(settings)')}
    for column in ['utah_additions','utah_subtractions','utah_exemptions']:
        if column not in existing_columns: db.execute(f"ALTER TABLE settings ADD COLUMN {column} TEXT DEFAULT '0'")
    ensure_year(year)
    db.execute('INSERT OR IGNORE INTO app_preferences(id,tax_year) VALUES(1,?)',(year,))
    db.commit()
def ensure_year(year):
    get_db().execute('INSERT OR IGNORE INTO settings(tax_year) VALUES(?)',(year,))
def close_db(error=None):
    db = g.pop('db',None)
    if db is not None: db.close()
def rows(table, year):
    if table not in {'transactions','partners','investment_transactions','investment_income','mileage_entries','tax_payments','documents','review_items'}: raise ValueError('Unknown table')
    return [dict(r) for r in get_db().execute(f'SELECT * FROM {table} WHERE tax_year=? ORDER BY id DESC',(year,))]
