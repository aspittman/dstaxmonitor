# DSTaxMonitor

Local tax readiness, bookkeeping, document organization, and deterministic tax estimates for DevSpace Technologies LLC and its owner's personal investments. A compact monitoring dashboard runs in your browser, with all application data on your computer.

**This is an estimation and accountant handoff tool, not tax advice, tax return preparation software, or an IRS filing system.** “Approved” means a user has reviewed a record; it never establishes legal deductibility. Use your human preparer to review eligibility, allocations, adjustments, and the final return.

## Linux quick start

Run these commands **inside this existing DSTaxMonitor directory**. Python 3.10 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m flask --app app:create_app init-db
python app.py
```

Open **http://127.0.0.1:5000**. Stop with Ctrl+C. Initialization also runs automatically on startup and preserves existing records. Debug mode and the reloader are disabled. Flask is the sole external runtime dependency; SQLite, Decimal, CSV and ZIP support use Python's standard library.

If Linux lacks venv support, install your distribution's `python3-venv` package first. A port conflict means another application is already using port 5000; stop that application before starting this one.

## First configuration

1. In Settings, select your tax year and filing status. Confirm full-year Utah residency is appropriate. Changing year loads independent settings rather than copying the old year's financial values.
2. In Business, add all partners. Ownership, profit and loss allocations must each sum to 100%; identify exactly one partner as you. Do not set your allocation to 100% simply because you operate the business.
3. Configure partner self-employment treatment after accountant review. Multi-member LLC status alone is not sufficient to determine SE treatment. Record your own Social Security wages and household Medicare wages separately from taxable other income.
4. Add business income/expenses and mileage. New form entries default to Needs Review. Only Approved records feed the estimate. Possible and Excluded entries remain in bookkeeping and exports.
5. Add personal investment lots and dividend/interest records; upload supporting redacted evidence. Record other taxable income (including W-2 taxable wages) in Settings. Personal transactions are bookkeeping records only and are not automatically included in the personal estimator; include taxable personal income once in Settings or investment income as applicable.
6. Record estimated payments and withholding. Enter a particular withholding amount either in Payments or Settings, never both. “Other” payments are tracked but not credited to the modeled federal/Utah tax position.
7. After review with your preparer, confirm scope, QBI deduction, adjustments, and completeness flags. Inspect Tax Estimate and the readiness blockers. Generate an accountant package whenever useful, including while incomplete.

Year-selected records are calendar-year inputs, with no automatic annualization. You can record expected-year entries intentionally, but this is not a cash-flow forecast. The global year selector in Settings filters all screens, CSV imports, uploads, exports and allocations. Business name/classification are shared across years; tax assumptions and partner allocations are year-specific.

## Tax calculation architecture and current limitations

`services/tax_engine.py` accepts normalized dictionaries and explicit rule sets, with **no database or HTML access**. Monetary arithmetic uses Decimal; SQLite stores monetary values as decimal text. Arithmetic retains precision internally and display rounds half-up to cents. Export JSON preserves exact decimal strings; displayed sums may differ by a cent from independently rounded components.

The calculation order is:

- Approved business revenue minus approved expenses and date-specific approved mileage.
- Configured profit allocation, or configured loss allocation if profit is negative.
- Approved realized short/long capital gains and losses netted across categories; ordinary loss deduction limited by filing status. Unrealized positions never count as realized gains.
- Allocated business share plus other taxable income, taxable interest and dividends, less manually reviewed adjustments and the deductible half of regular SE tax.
- Basic standard deduction and an accountant-reviewed manual QBI amount; ordinary brackets and stacked preferential capital gain/qualified dividend brackets, including the ordinary-tax ceiling.
- Regular SE tax under the configured active-partner assumption, the wage cap, and Additional Medicare tax.
- Separate Utah gross-tax component and a future verified Utah credit module.
- Complete component totals minus federal/Utah payments and withholding; compare the signed estimated balance with reserve.

Every trace record includes section, label, input, rule applied, calculation, result, year, version, source, and verification date. Tax Estimate exposes these in expandable panels. Exports include the full precision trace and the rule snapshot used.

**The bundled 2026 Utah estimate is intentionally incomplete.** The enacted 4.45% rate is verified, but the available Tax Commission 2026 TC-40 is a draft dated September 28, 2026. Final credit rules are not asserted as verified. The UI shows estimated Utah gross tax *before credits* under the zero-state-adjustment assumption, and withholds final Utah tax, combined total, combined remaining tax and reserve surplus/shortfall. This is deliberate: a rate alone is not a final Utah tax calculation. A verified federal component can still be displayed once required configuration/review is complete. What-If shows a federal income-tax component comparison while combined totals are unavailable.

Standard deduction scope is an adult under 65, not blind, not a dependent, and not itemizing. No automatic tax credits, QBI eligibility/minimum deduction computation, itemized deductions, depreciation, AMT, NIIT, prior loss carryforwards, partnership basis/at-risk/passive limitations, guaranteed payments, spouse SE calculation, foreign income, special capital-asset rates, or wash-sale detection. A loss allocation is displayed but never automatically allowed as a personal deduction. High income triggers an incomplete federal warning because special taxes may apply. Imported/entered basis must already reflect accountant/broker-reviewed adjustments. Qualified dividends must satisfy reviewed eligibility/holding requirements; enter the qualified portion separately from ordinary dividends to avoid double counting. Crypto support covers ordinary purchase/sale lots, not staking, mining, swaps, DeFi, or automatic lot matching.

QBI and adjustments are manual reviewed inputs, not legal determinations. The What-If tool does not change records and recalculates allocation and SE effects, but keeps the manual QBI deduction fixed; scenarios may require a new QBI review. A hypothetical business expense is not a dollar-for-dollar tax credit and is not declared deductible by this tool.

## Rule sources and verification

Versioned rules live at `tax_rules/<year>/federal.json` and `utah.json`. Metadata records `tax_year`, `jurisdiction`, `version`, `source_name`, `source_url`, `last_verified`, `verified`, notes and parameter-specific source references. Parameter verification date: **2026-09-30**.

Authoritative sources checked for the bundled parameters:

- [IRS Revenue Procedure 2025-32, 2025-45 Bulletin](https://www.irs.gov/irb/2025-45_IRB): 2026 ordinary brackets, standard deduction and preferential capital gain thresholds.
- [IRS Notice 2026-10](https://www.irs.gov/irb/2026-04_IRB): business mileage 72.5¢/mile through June 30.
- [IRS Announcement 2026-11](https://www.irs.gov/irb/2026-29_irb): business mileage 76¢/mile from July 1.
- [IRS 2026 Publication 505](https://www.irs.gov/pub/irs-prior/p505--2026.pdf): regular SE earnings factor, minimum, rates, half-SE adjustment and 2026 wage cap.
- [SSA 2026 contribution base](https://www.ssa.gov/oact/cola/cbb.html): $184,500 Social Security base.
- [IRS Topic 560](https://www.irs.gov/taxtopics/tc560): Additional Medicare rate and filing-status thresholds.
- [IRS Topic 409](https://www.irs.gov/taxtopics/tc409) and [Publication 544](https://www.irs.gov/publications/p544): capital gain/loss netting, loss limits and holding periods. These ongoing general provisions are recorded in the selected year's rules; no older annual brackets are reused.
- [IRS QBI deduction explanation](https://www.irs.gov/newsroom/qualified-business-income-deduction): basic taxable-income ceiling; the 2026 active-business minimum is not computed here and needs accountant review.
- [Utah enrolled SB 60](https://le.utah.gov/Session/2026/bills/enrolled/SB0060.pdf): enacted 4.45% individual rate, retrospective to January 1, 2026.
- [Utah Tax Commission draft TC-40](https://files.tax.utah.gov/tax/forms/drafts/tc-40.pdf): inspected and deliberately **not** used as verified final credit authority.

No runtime scraping, LLM tax decisions or automatic updates occur. A Verified badge means checked parameters, not coverage of all tax law. Missing, mismatched-year or unverified rule sets never fall back to a previous year. Separate parameter verification allows the enacted Utah gross-rate component while the complete state rule set remains unverified.

### Add a future year

1. Add `tax_rules/<new-year>/` in version control. Create independent federal/state files with matching metadata, mark unavailable parameters unverified and leave them null.
2. Check authoritative sources for every numeric parameter and effective date. Preserve date ranges for midyear mileage changes.
3. Add fixed financial fixtures and boundary tests, update metadata/version, and review the diff with your preparer before marking rules verified. Do not merely copy a prior year and change `tax_year`.
4. Choose the new year in Settings and configure that year's partner allocations and assumptions.

The federal schema can reuse the deterministic engine across supported years. `services/state_tax_service.py` supports a verified Utah taxpayer-credit schema: `exemption_amount`, `deduction_factor`, `phaseout_rate` and status-keyed `phaseout_thresholds`, together with reviewed Utah additions, subtractions and qualifying exemption counts in Settings. This module stays disabled for bundled 2026 because its final parameters are unverified. Additional credits or new law may need a new module and tests; setting `verified=true` alone is insufficient. Other states and entity types should get distinct modules rather than changing partnership arithmetic silently.

## CSV import and review

Transactions, investment lots, investment income and mileage have downloadable CSV templates in their sections. Include all template headers; optional cells can be blank. UTF-8 (including BOM), ISO dates (`YYYY-MM-DD`) and decimal numbers without `$` or thousands separators are accepted. Dates must match the selected year except acquisition dates. A sale date is optional for unrealized positions. Basis/proceeds can be blank while Needs Review, but approved realized lots require both. Quantity must be positive.

Import validates the whole file before saving anything. Maximum 10,000 rows / 16 MB. Every row specifies a review status; use `Needs Review` until checked. **Reimporting creates duplicates**; there is no automatic broker-ID matching in V1. Edit incorrect entries or mark duplicate records Excluded. No financial delete workflow is exposed.

`IMPORT_ADAPTERS` in `services/transaction_service.py` is the extension point for broker-specific adapters such as Alpaca. An adapter returns normalized validated records; add tests for its actual CSV schema. No live brokerage connection exists.

Expense categories are bookkeeping labels, not eligibility rules. Filters support scope, income/expense, category, status, missing/attached receipt and review queue; tables can be sorted by clicking or keyboard-activating their column headings.

## Documents and database

- `data/dstaxmonitor.sqlite3`: SQLite database with foreign keys and schema version tracking.
- `data/session.key`: private local session signing key.
- `uploads/`: safe UUID-named PDF/PNG/JPEG files; never under static.
- `exports/<year>/<timestamp-id>/`: accountant package, plus adjacent ZIP.
- `tax_rules/`: nonsensitive reviewable versioned rules.

Normalized tables: `settings`, `app_preferences`, `businesses`, `partners`, `transactions`, `investment_transactions`, `investment_income`, `mileage_entries`, `documents`, `tax_payments`, `tax_rule_versions`, `review_items`, `schema_migrations`.

Document metadata includes name, type, category, year, associated business/transaction/investment/payment, upload time, notes, review status, private generated filename and SHA-256 digest. Metadata can be edited without changing the original file. File signatures and extensions are checked; only protected ID-based local view/download routes serve documents. A missing file remains visible as missing evidence. Readiness requires actual files and Approved status, not metadata alone. Demo metadata deliberately does not count as evidence.

Initialization is idempotent and has an additive settings-column migration. Future migrations should be explicit and backed up before applying. Important financial data is never stored in localStorage.

## Readiness and accountant export

Readiness averages visible completeness checks: income reconciliation, reviewed/categorized transactions, receipt evidence, reviewed mileage and completeness, partner allocations, investment reconciliation, conditional investment tax forms, partnership/K-1 documents, K-1 confirmation, payment evidence, verified estimate scope/rules, and unresolved items. Flags are year-specific user confirmations; not inferred from the date. The dashboard shows exactly which checks remain incomplete. Completeness is not legal filing approval.

Accountant Export generates a dated, year-specific directory and ZIP containing:

- Business revenue/expenses/mileage summary and approved expenses by category.
- Detailed transactions, mileage, partner allocations and payments as CSV.
- Personal investment trade/income CSVs and gain/loss summaries.
- Tax estimate JSON, full calculation CSV, normalized year settings and rule snapshots.
- Readiness issues and custom review items.
- Document index with metadata/evidence status and unchanged copies of original uploaded files.
- README describing scope and demo/incomplete status.

CSV text beginning with spreadsheet formula characters is prefixed with an apostrophe. Originals are never modified. ZIP creation does not send anything to the IRS or anyone else. Export directories retain their data for review; manage retention locally after backups.

## Backups and security

**This contains sensitive financial information. Do not expose it to the public internet, bind it to `0.0.0.0`, port-forward it, or place it behind a public tunnel/proxy.** It is intended for a trusted single-user local computer, with no authentication or multi-user permissions.

The server binds to `127.0.0.1`. Independent Host and peer-IP checks reject external access and DNS-rebinding hosts. CSRF tokens, same-origin checks, Strict/HttpOnly cookies, a restrictive content policy, frame blocking and no-store headers protect local browser workflows. No external fonts, scripts or integrations load. Do not override these protections to publish it. The development server is used only for this local application.

Data directories are restricted to the OS user, database/session key/uploads/ZIP files have private permissions, but **data is not encrypted at rest**. Use disk encryption, a locked OS account and encrypted backups. Other processes running as your user can read the data. Do not run on an untrusted/shared account. PDF/image validation is not malware scanning or an SSN detector; upload trusted redacted documents only.

V1 has no SSN, password, banking-login, brokerage-credential, or IRS-credential fields. Do not enter such secrets in notes or upload unredacted forms containing them. It does not log document contents. Normal Flask request logs include routes; avoid placing private details in query strings.

For a consistent backup:

1. Stop the server.
2. Back up **data, uploads and exports together**, plus the rule files and source version. Backing up only SQLite leaves document references without evidence.
3. Store the backup encrypted off-device with access limited to you.
4. Restore the directories into the same configured workspace, preserve restrictive permissions, initialize safely, and check Tax Vault/downloads and exported document indexes.

`.gitignore` excludes local databases, session keys (all data contents), uploaded evidence, generated exports, `.env`, virtual environments, logs and Python caches. Only `.gitkeep` placeholders are allowed in the three data directories. Review `git status` and `git ls-files` before committing; ignoring a file does not untrack an already tracked file.

## Download a complete backup / restore

Open **Settings → Full workspace backup → Back Up Now**. Your browser downloads
`DSTaxMonitor-backup-<UTC timestamp>.zip`. Upload that ZIP to your private Google
Drive manually. This does not connect the app to Google or send data automatically.
The ZIP contains all tax years (regardless of the selected year), a consistent
SQLite snapshot, uploaded document files, existing accountant exports, tax rules,
and the application source needed to restart it. Temporary downloads are not saved
in the exports directory, so later backups do not contain previous backup ZIPs.

The SQLite backup API takes a consistent database snapshot while the app runs.
Finish edits/uploads before clicking the button; it is best to avoid changing
records until the download completes. A manifest lists checksums and any evidence
files that were already missing. Missing files cannot be recreated by a backup.
The ZIP is not encrypted: restrict access in Drive and protect your account.

To recover on another Linux computer, install Python 3.10 or newer, download your
backup and obtain `restore_backup.py` from the ZIP or a trusted application copy:

```bash
python3 restore_backup.py /path/to/DSTaxMonitor-backup.zip --destination /path/to/new-empty-folder
cd /path/to/new-empty-folder
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

The restore tool verifies every packaged file before writing, rejects unsafe ZIP
paths, and refuses to overwrite an existing workspace. It validates SQLite integrity,
restores private file permissions and creates a fresh session key at startup.
Open http://127.0.0.1:5000 and verify transactions and Tax Vault downloads before
retiring the old computer or backup. Virtual environments and dependencies are
reinstalled, not copied. Checksums detect corruption rather than authenticate
untrusted archives; restore only backups you created. Additional instructions
are included in `RESTORE.txt` inside each ZIP.

## Optional isolated demo

The real workspace starts empty. For an isolated demo, stop any server on port 5000 and run:

```bash
python app.py --data-dir /tmp/dstaxmonitor-demo --demo
```

This uses a separate local database, upload directory and exports in `/tmp/dstaxmonitor-demo`. Synthetic transactions, partner allocation, mileage, trades, dividends, interest, payments and missing-file document metadata demonstrate workflows. A persistent banner identifies demo mode. Restart the same workspace with the same command; already seeded demo data is preserved. The Settings demo button and `flask seed-demo` command only seed an empty year and refuse to mix with existing records. Test fixtures and synthetic Utah credit fixtures are never loaded into real data or rules.

## Verification

```bash
python -m unittest discover -s tests -v
```

Tests isolate databases/documents/exports in temporary directories. Fixed financial tests cover profit/allocation/status filtering, midyear mileage, calendar holding periods, missing basis, capital netting/loss limits, federal bracket boundaries, preferential stacking, SE wage cap/minimum/adjustment, payments/reserve balances, What-If immutability, trace metadata and missing/unverified/mismatched-year behavior. A clearly synthetic verified-state fixture tests the final-total pipeline without claiming actual Utah credit law. Workflow tests cover initialization, all screens, CSRF/Host/peer checks, uploads/view/download/edit/association, atomic imports, review filters, separate years, demo isolation, formula-safe CSV output and ZIP contents with unchanged document copies.

## Extension points / next step

Services separate routes, financial calculations, business, investment classification, state rules, records/adapters, document storage, readiness and exports. The next priority is an accountant-reviewed final 2026 Utah rule set and full state adjustment/credit coverage, followed by reviewed QBI calculation and broader return assumptions.

Future Alpaca/bank imports, OCR, receipt matching, monthly close, reminders, backups and form preparation should implement tested adapters/services with explicit review states. No live brokerage, cloud backup, email, form generation, tax-software integration or e-filing is implemented in V1.
