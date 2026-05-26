# Changelog

All notable changes to the **Qota App** will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Billing — Automatic Billing Job:** New Frappe scheduler event (`weekly`) calls `qota.billing.tasks.run_monthly_billing_cycle`. When `Auto Billing` is enabled in Billing Settings, the job automatically creates and submits a Billing Cycle (basis `All`) for the previous calendar month. Runs weekly so the cycle is created promptly even if the scheduler fires late. The job is idempotent: it skips silently if a cycle already exists for the target period, and writes to the Error Log if the Billing Year is missing or cycle creation fails. New `auto_billing_enabled` Check field added to Billing Settings (Cycle & Operations section).

- **Governance — Service Reconnection Order (Print Format):** New Jinja print format (`qota/governance/print_format/service_reconnection_order`) for the `Service Reconnection` DocType. Displays subscriber info, reconnection details (previous suspension, type, reason, fee or "Free Reconnection", status, execution date, initial reading for metered), remarks, and two signature lines (Authorized By / Technician). Accent color: `#2d98da` (sky blue).

- **Governance — Service Contract (Print Format):** New Jinja print format (`qota/governance/print_format/service_contract_summary`) for the `Service Contract` DocType. Displays subscriber info, contract details (status with color, billing basis, category, start date, meter ID, cistern, suspension info), and a live account statement table with all outstanding Debt Ledger Entries and total. Single signature line. Accent color: `#2c3e50` (navy).

- **Billing — Connection Bill (Print Format):** New Jinja print format (`qota/billing/print_format/connection_bill`) for the `Connection Bill` DocType. Displays subscriber info, connection details (amount, status with color), description, and single signature line. Accent color: `#e67e22` (amber).

- **Billing — Payment Receipt (Print Format redesign):** Redesigned the `Payment Receipt` Jinja print format to match the unified visual style used across all Qota print formats: centered company header with accent color, subscriber info in label/value table, items table with alternating rows, totals section with accent footer, remarks with left-border accent, two-column signature lines, and standard Qota footer. Accent color: `#00b894` (teal/green). Replaced CSS-class-based layout with inline styles for reliable wkhtmltopdf rendering.

- **Billing — Debt Refinancing Agreement (Print Format):** New Jinja print format (`qota/billing/print_format/debt_refinancing_agreement`) for the `Debt Refinancing` DocType. Displays company header, subscriber info (name, ID, billing basis, premises location), refinancing summary table (original debt, down payment, financed amount, installments, monthly payment, first installment date), full amortization schedule with status per row (Pending/Billed/Paid), a formal agreement paragraph, and two signature lines (Authorized By / Subscriber). Color accent `#6c5ce7` (purple). All strings use `_()` for translation. Spanish translations added for all new UI strings.

- **Governance — Service Reconnection: `service_contract` field:** New required `Link` field added to the `Service Reconnection` DocType. The form now starts by selecting a `Suspended` contract; the corresponding executed suspension is auto-filled (read-only). All `fetch_from` fields (`subscriber`, `full_name`, `premises`, `billing_basis`) now derive from `service_contract` directly instead of going through `service_suspension`.

- **Patches — `backfill_reconnection_service_contract`:** One-time patch that populates `service_contract` on all existing `Service Reconnection` records by reading the value from the linked `Service Suspension`.

- **Billing Workspace Sidebar — reorganization and icons:** Added `Transactions` section grouping Payment Receipt and Debt Refinancing. Moved Billing Cycle into a new `Setup` section alongside Billing Settings. Removed orphan `Benefit` sub-section. Added missing icons to all items (Billing Year, Service Rate, Discount Rule, Benefit Discount, all report entries). Reports section now defaults to open (`keep_closed: 0`).

- **Billing — Connection Bill: `status` field:** New `Select` field (`Draft` / `Unpaid` / `Paid` / `Cancelled`) added to `Connection Bill`. Set to `Unpaid` on submit and `Cancelled` on cancel. `sync_reference_document_status` on the Debt Ledger Entry updates it to `Paid` when the linked DLE is fully paid.

- **Patches — `backfill_connection_bill_status`:** One-time patch that derives the correct status for all existing `Connection Bill` records from their `docstatus` and linked Debt Ledger Entry status.

- **Billing — Debt Refinancing: full ledger flow on submit:** `on_submit` now (1) zeroes all outstanding Debt Ledger Entries for the contract and syncs their reference documents to `Paid`, (2) creates a `Refinancing Down Payment` DLE due immediately if a down payment is set, and (3) creates one `Refinancing Installment` DLE per amortization row with the row's due date.

- **Billing — Debt Ledger Entry: new entry types:** Added `Refinancing Down Payment` and `Refinancing Installment` to the `entry_type` select on `Debt Ledger Entry` and `payment_concept` on `Payment Receipt Item`. Both types use `days_to_add = 0` (due immediately).

- **Billing — Debt Refinancing: `get_contract_balance` fix:** Query was summing `amount` (original) instead of `outstanding_amount`, and had no filter for cancelled or already-paid entries. Fixed to `SUM(outstanding_amount)` with `outstanding_amount > 0.01 AND docstatus != 2`.

- **Billing — Debt Refinancing: suspended contracts selectable:** `service_contract` selector now includes `Suspended` contracts in addition to `Active`.

- **Patches — `backfill_service_reconnection_status`:** One-time patch that corrects `Service Reconnection` records whose `status` was set to `"Unpaid"` by the old `sync_reference_document_status` logic. Derives correct status from `docstatus`, `reconnection_fee`, and linked DLE payment state.

### Fixed

- **Service Suspension — `docstatus = 1` filter on Debt Ledger Entry:** `validate_suspension_rules` (both Administrative and By Request branches) was filtering `Debt Ledger Entry` with `docstatus = 1`. Since `Debt Ledger Entry` is not submittable (`docstatus` is always 0), the query always returned empty and administrative suspensions failed with "no expired debts" even when debt existed. Fixed to `docstatus != 2`.

- **Patch `fix_monthly_bill_status_from_debt_ledger` — same `docstatus = 1` issue:** Same incorrect filter on `Debt Ledger Entry` in the historical patch. Fixed to `docstatus != 2`.

- **Service Reconnection — `default_reconnection_fee` field not found:** JS and Python were referencing a non-existent `default_reconnection_fee` field in `Billing Settings`. Corrected to `reconnection_fee_item`.

- **Payment Receipt — suspended contracts not selectable:** The `service_contract` selector was filtering only `Active` contracts, preventing payment of reconnection fees for suspended contracts. Filter updated to include `Suspended` status.

- **Payment Receipt — "Add Monthly Advance" shown for suspended contracts:** The advance button was visible regardless of contract status. It is now hidden when the contract is `Suspended`, since suspended contracts cannot receive future billing advances.

- **Debt Ledger Entry — `sync_reference_document_status` overwrote workflow statuses:** For submittable documents (Service Reconnection, Connection Bill), the sync was pushing `"Unpaid"` / `"Partially Paid"` directly, overwriting statuses like `"Pending Payment"` and `"Executed"`. Fixed so that for submittable doctypes, the sync only acts when `status == "Paid"`.

- **Service Reconnection — `"Pending Payment"` renamed to `"Unpaid"`:** Status value aligned with the rest of the system so `sync_reference_document_status` can push `"Paid"` / `"Unpaid"` without any translation layer. Updated in JSON, controller, JS, and backfill patch.

---

## [16.8.0] - 2026-05-25

### Added

- **Governance — Delinquency Notice (Print Format):** New Jinja print format (`qota/governance/print_format/delinquency_notice`) for the `Service Contract` DocType. Displays company name and service label from Billing Settings, subscriber info (name, ID type/number, billing basis, sector, block, house, address reference), a live account statement table with all outstanding Debt Ledger Entries (period, type, charged, paid, outstanding, due date), total outstanding, and a formal notification paragraph urging payment to avoid suspension. Single centered signature line (Authorized By). All strings use `_()` for translation.

- **Translations — Spanish (es.csv):** Created `qota/translations/es.csv` with Spanish translations for all print format and system strings, including the new Delinquency Notice and Debt Ledger Entry validation messages.

### Fixed

- **Debt Ledger Entry — `make_debt_ledger_entry` due date anchored to today:** `due_date` was always calculated from `today()` regardless of the billing period, causing retroactive entries to have incorrect due dates. Added `reference_date` parameter; callers can now pass an explicit anchor date. `Monthly Bill` passes `self.end_date` so the due date is correctly calculated as bill end date + `days_until_due`.

- **Debt Ledger Entry — duplicate entries not prevented:** `make_debt_ledger_entry` had no duplicate check. Added validation that raises an error if a Debt Ledger Entry of the same `entry_type` already exists for the same `service_contract` and `billing_period`.

- **Debt Ledger Entry — incorrect grace period for Late Fee and Reconnection Fee:** `Late Fee` and `Reconnection Fee` were using `grace_period` as their due date offset. Both types are now explicitly set to `days_to_add = 0` (Late Fee is already overdue when generated; Reconnection Fee must be paid immediately).

---

## [16.7.1] - 2026-05-07

### Changed

- **Reports — Block and House No. columns:** `fieldtype` changed from `Data` to `Int` in Delinquent Subscribers and Scheduled Suspensions reports so Frappe renders and sorts them numerically. Both reports now default sort order to Block ASC, House No. ASC.

- **Premises — Sector, Block and House Number validation and normalization:** `validate_integer_fields` added to the `Premises` controller. On save, each field is parsed with `int()`: non-integer values throw a descriptive error, and values with leading zeros (e.g. `"09"`) are normalized to their canonical integer string (`"9"`) before persisting.

---

## [16.7.0] - 2026-05-07

### Added

- **Governance — Delinquent Subscribers Report:** New Script Report (`qota/governance/report/delinquent_subscribers`) listing active or suspended service contracts with outstanding monthly fee debt. Columns: Contract, Subscriber Name, Block, House No., Contract Status, Overdue Periods, Total Outstanding, Advance Balance, Net Outstanding, Oldest Unpaid Period, Suspension. Filters auto-load `suspension_months_limit` and `min_debt_for_suspension` from Billing Settings. Advance balance (unapplied `Payment Receipt Item` balances for Monthly Fee) is subtracted from gross outstanding so subscribers who pre-paid at an old rate and have a surplus are not incorrectly flagged.

- **Governance — Scheduled Suspensions Report:** New Script Report (`qota/governance/report/scheduled_suspensions`) listing service suspensions filtered by status (Scheduled by default). Columns: Suspension, Subscriber Name, Sector, Block, House No., Contract, Suspension Type, Reason, Effective Date, Outstanding. Includes a "Print Selected" button that opens the suspension notice print format for each checked row.

- **Governance — Service Suspension Notice (Print Format):** New Jinja print format (`qota/governance/print_format/service_suspension_notice`) for the `Service Suspension` DocType. Displays company name from Billing Settings, subscriber info, premises location (sector, block, house, address reference), suspension details (type, reason, effective date, outstanding debt calculated live from Debt Ledger Entry), a formal notification paragraph, and signature lines for the responsible party and subscriber/witness. All strings use `_()` for translation. Spanish translations added for all UI and print strings.

- **Billing — Add Missing Bills (Monthly Bill list):** New button in the Monthly Bill list view that opens a dialog to generate historical bills for any contract without altering the Service Contract. The dialog accepts a Service Contract (auto-fills Subscriber Name and Premises with block/house description) and a closed Billing Year. Clicking Search shows all missing months as checkboxes; the user selects the specific months to generate and clicks Generate Selected. Bills are created in ascending order with the billing continuity check bypassed for this operation. New backend methods: `get_missing_periods_for_contract` and `generate_bills_for_periods` in `qota/billing/utils.py`. The `validate_sequence` in `Monthly Bill` respects `frappe.flags.skip_billing_continuity_check` to support this flow.

### Fixed

- **Billing Dashboard — Generate Missing Bills:** `generate_bills_and_link_advances` now sorts gaps by year and month ascending before creating bills, preventing the billing continuity validation from failing when multiple months are pending.

- **Monthly Bill status out of sync with Debt Ledger Entry:** Added patch `qota.patches.fix_monthly_bill_status_from_debt_ledger` to correct historical records where a Monthly Bill remained `Unpaid` or `Partially Paid` even though its corresponding `Debt Ledger Entry` had already been fully paid. The patch cross-references each stale bill against its DLE via `reference_name` and applies the correct status. Zero inconsistencies remain after execution.

- **Service Suspension — cancel error `Unknown column 'remarks'`:** `cancel_linked_meter_readings` was filtering `Meter Reading` by a `remarks` field that does not exist in that DocType. Removed the invalid filter; method now queries by `service_contract` and `docstatus = 1` only.

- **Service Suspension Notice — Jinja syntax error `unexpected '/'`:** Section divider comments were written as `{{- /* ... */}}` (C-style), which is invalid Jinja2. Replaced all instances with `{# ... #}`.

### Changed

- **Connection Bill:** Updated DocType metadata (`modified` timestamp) after local configuration adjustments.
