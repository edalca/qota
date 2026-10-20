# AGENTS.md

## Purpose and authority

This file is the authoritative current architecture and product contract for
Qota. It applies to every human and agent changing this tree. The code,
fixtures, and patches are the evidence. When this file and the code disagree,
trust the code and update this file in the same change.

A checkout may add local workflow in `AGENTS.local.md`. That file cannot
weaken this contract, and a published clone does not require it.

Do not describe unimplemented behavior as current law.

## Product identity

Qota is the Frappe app for a community water board (Junta Administradora de
Agua). It bills the service, keeps the debt ledger, records payments, and
suspends and reconnects service.

The app name is `qota`. The version constant is `__version__` in
`qota/__init__.py` (16.9.0 at the time this contract was written). Frappe
owns the framework; this repository is only the Qota app. Select field values
and DocType names stay English. Spanish is translation, in
`qota/translations/es.csv` and `qota/locale/es.po`.

Qota owns only the business, administrative, and operational domain of the
water board. Messaging, conversations, channels, notifications, and chatbot
automation belong to an independent platform and are not dependencies or
modules of Qota.

Production is a separate site. This tree is not deployed there by editing
files here.

## Modules

`qota/modules.txt` lists three modules, in this order:

- `Governance` holds subscribers, premises, contracts, suspensions,
  reconnections, and institutional settings.
- `Billing` holds charges, receipts, refinancing, rates, and billing setup.
- `Expenditures` holds expense vouchers and categories.

A DocType stays in the module that owns its files under
`qota/<module>/doctype/`. Menu changes do not move DocTypes between modules.

## Desk navigation

Frappe 16.50 and later splits navigation into three steps:

1. Desktop shows one icon per app. Qota is registered in
   `add_to_apps_screen` in `qota/hooks.py`. The `name` must be the app name
   `qota`. A display title such as `Qota` does not attach the dock.
2. The dock is the narrow column of sidebar icons. The shipped dock is
   `qota/dock/qota/qota.json`, in this order: Collection, Billing,
   Governance, Expenditures. Opening the app lands on Collection.
3. A module keeps the sidebar titled with its name, because that is the
   sidebar the desk uses for the module. A module may also own extra
   sidebars. Each sidebar has its own desk URL, so a refresh stays on that
   sidebar. DocTypes stay in their modules.

The apps screen hides the dock. The dock appears after the app icon is
opened. `Desktop Settings` → `Desktop Page` = `Apps` is the new home. `Desktop
Icons` is the old grid.

The four operational sidebars use the icons in `qota/public/icons/icons.svg`.
The drawings stay the ones Qota authored. They paint like the Framework soft
module icons: `currentColor` strokes, a 10% body and one 50% accent, through
Frappe's `soft-icon` classes, so a tile's ink carries hover, active and dark
mode. Hover motion and `prefers-reduced-motion` stay. Symbol ids stay. The
app mark remains the teal drop in `logo.svg` and `favicon.svg`.

- `Collection` (Cobro), module Billing, icon `collection-cash-duotone`.
  The glyph is an old cash register: a square body and a small display.
  The drawer slides open on hover. Opens on Payment Receipt. Items: Payment Receipt, Debt Refinancing, then
  Reports (Daily Collection, Customer Statement, Advance Payments,
  Advances and Surplus). File:
  `qota/billing/sidebar/collection/collection.json`.
- `Governance` (Gobernanza), destination sidebar `Subscribers`, module Governance, icon
  `subscribers-card-duotone`. Opens on Subscriber. Items: Subscriber,
  Premises, Service Contract, then Operations (Service Suspension, Service
  Reconnection), then Reports (Delinquent Subscribers, Service
  Suspensions), then a final root Governance Settings link to Institutional Settings. File:
  `qota/governance/sidebar/subscribers/subscribers.json`.
- `Billing` (Facturación), icon `billing-drop-duotone`. Opens on Monthly
  Bill. Items: Monthly Bill, Connection Bill, Meter Reading, Service Fine,
  then Masters (Billing Year, Service Rate, Discount Rule, Benefit
  Discount), then Reports (Aging Report, Billing and Collections), then
  Settings (Billing Cycle, Billing Settings).
- `Expenditures` (Gastos), icon `expenditures-coin-duotone`. Opens on
  Expense Voucher. Items: Expense Voucher, Expense Category.

`qota/governance/sidebar/governance/governance.json` stays titled
Governance and is not on the dock. It keeps one Home link to the Governance
workspace, so the shell is not empty and the desk does not recompute it
from the whole module. Subscriber, Premises, the contract, the cut, the
reconnection, and the two reports are listed on Subscribers, which is where
those screens open. Its header icon is `subscribers-card-duotone`. The
house symbol `governance-house-duotone` remains in the sprite and is unused.

Sidebar item labels and dock titles are stored in English. The desk
translates sidebar labels. `qota/public/js/dock_labels.js` translates the
dock titles when drawing. Do not save the translated words back onto the
Dock Item.

The app mark and favicon are the flat drop in `qota/public/logo.svg` and
`qota/public/favicon.svg`. These files are served from the app `public/`
tree. A browser can keep the previous SVG for hours. A hard reload picks up
a new sprite. `bench build` is not required for these files.

The legacy `qota/workspace_sidebar/` format was removed; Frappe 16.50 sidebars
live in `<module>/sidebar/<name>/<name>.json`.

A pinned dock stays visible. A floating dock stays off-screen until the
pointer touches the left edge.

## Billing

Charges are Debt Ledger Entry documents. The customer statement debits every
ledger amount and credits every submitted Payment Receipt Item amount, plus
one credit per submitted Debt Refinancing equal to its current total debt.
The running balance is debits minus credits. A prepaid position can be
negative while some ledger rows still show an outstanding amount.

Payment Receipt derives `current_debt` in backend validation from
`get_pending_balances`: outstanding ledger debt before the receipt is applied.
`total_pending` snapshots the remaining debt after the receipt's projected,
bounded applications, using the same amount rule as ledger processing. Draft
save and Submit refresh both values; frontend values are only a preview.
Advances and unused surplus do not reduce this pending-debt summary. These
informational snapshots are not the reconciled net balance from `read_balance`
and are not recomputed on historical submitted receipts.

A Monthly Fee advance covers a monthly charge only when the receipt item
concept is Monthly Fee and the billing period matches. Apply unused advance
to the oldest matching period first. The item `balance` is the unused
advance. The receipt header `unallocated_amount` can be stale.

Service Fine, on submit, creates only a Service Fine ledger entry. It does
not create a Service Suspension.

Do not reintroduce Refinancing Credit ledger entries. Debt Refinancing is
recorded by `qota.patches.v16_9_0_record_refinanced_debts`.

Delinquent Subscribers counts a month only when its due date plus grace is
before today and unused Monthly Fee advance does not cover it, oldest first.
Net outstanding may be negative. Rows with net at or under 0.01, or with
fewer uncovered periods than the minimum, are excluded.

### Balance summary reader

`qota.billing.balance_summary` is an internal read-only reader without
whitelist. It requires System Manager, ordinary read permissions, and a
submitted `Active` or `Suspended` contract. It reuses the ledger, submitted
receipts, unapplied balances, `settled_debts`, refinancing schedules, and
Customer Statement readers for reconciliation. It never invokes generators,
advance applications, receipt processors, submit/cancel, or synchronizers. It
uses `Decimal` and SQL text casts before driver conversion; MariaDB preserves
nine decimals and Billing settles to `0.01`. It verifies `HNL` in `Billing
Settings`.

The typed `Verified` / `Unavailable` / `TechnicalFailure` result retains the
Honduras cutoff date, totals for monthly fees, fines, surcharges, and
additional charges, ledger references, aggregated evidence, and reading
digest. It never exposes amounts on an unverified result. Unapplied `Monthly
Fee` advances cover only that concept and period, oldest first, without
double-subtracting payments already reflected in `outstanding_amount`. Due
dates and source documents determine which monthly fees, fines, and surcharges
are current; grace days do not exclude debt.

`Connection Fee`, `Reconnection Fee`, `Other Fee`, `Refinancing Down Payment`,
and `Refinancing Installment` are included when `due_date` is on or before the
cutoff date; future charges are excluded. Sources, schedules, and settlements
are reconciled without double-counting settled originals or fabricating
`Refinancing Credit`. Any unknown concept fails closed with `Unavailable`.

## Governance

Service Suspension is the only service cut. `suspension_type` is the reason.
The options are `Subscriber Request`, `Arrears`, and `By Fine`. There is no
separate reason field. A physical `reason` column may still exist in the
database. Do not add the field back.

`By Fine` must link an unpaid submitted Service Fine for that contract.

Submit moves a draft suspension to `Scheduled`. Confirm Technical Cut calls
`execute_suspension_logic`, which sets `Executed`, writes `executed_date`,
sets the contract to Suspended, and for a metered contract creates a Meter
Reading. `executed_date` is the technical cut date. It can differ from
`effective_date` because the crew may arrive on another day.

An executed suspension cannot be cancelled. A scheduled suspension can be
cancelled when its Service Fine has no recorded payment. If that fine has
payments, those Payment Receipts have to be cancelled first. Cancelling a
scheduled order is how a programmed cut is withdrawn after the subscriber
catches up.

The reconnection fee is zero only when the last executed suspension type is
`Subscriber Request`.

The Service Suspensions report lists scheduled, executed, and cancelled
orders. Cancelled means the document was cancelled (`docstatus` 2): the
order had been programmed and was then withdrawn, which sets `status` back
to Draft. The desk name is Service Suspensions (Suspensiones de Servicio).

### Contract status summary reader

`qota.governance.contract_status_summary.read_status` is an internal read-only
reader without whitelist. It requires System Manager and ordinary document
permissions; child tables are authorized through their parents. A submitted
`Service Contract` in `Active` or `Suspended` status retains authority. It
never mutates contracts, orders, obligations, receipts, or meter readings. The
documentary cutoff uses `America/Tegucigalpa`.

`StatusResult` and `OrderStage` separate canonical contract status from each
`Verified`, `Unavailable`, or `TechnicalFailure` stage. A scheduled suspension
requires a submitted `Scheduled` order with `effective_date` and no execution,
cancellation, invalid amendment, or conflicting order. Reconnection checks the
link to the executed suspension and `suspended_since`, documentary uniqueness,
the `Reconnection Fee` obligation, and active receipt applications. Pending
reconnection synchronization returns to `Unpaid` when payments are reversed
and preserves `Executed` / `execution_date` once executed. Metered cuts use
`executed_date`, allow saving `final_reading` after submit, and submit a
single reading. Cancelling a `Scheduled` suspension preserves independent
meter readings.

## Institutional Settings and telephone capture

`Institutional Settings`, presented in desk as Governance Settings /
Configuración de Gobernanza, is the administrative Single of Governance,
restricted to System Manager with native `Version` change tracking. Its four
child tables manage weekly hours (`weekly_hours`), date exceptions
(`calendar_exceptions`), exceptional intervals (`exception_hours`), and
effective office locations (`office_locations`). No default schedule or
location is preloaded on install. A configured weekly schedule declares all
seven days; intervals are `[start, end)` without crossing midnight.

Below the weekly schedule table, the HTML calendar exceptions section manages
the hidden `calendar_exceptions` and `exception_hours` tables through three
native dialogs: Holiday (date only, `Closed`), Exceptional Hours (date, one
replacement interval, and mandatory `internal_reason`, `Open`), and
Extraordinary Closure (date and mandatory `internal_reason`, `Closed`).
`public_reason` stays empty and any public exception reason is rejected.
Dialogs mark the document dirty and refresh the section; only saving the
Single persists changes. `qota.governance.institutional` exposes internal
readers `office_information` and `is_within_office_hours` using
`America/Tegucigalpa`.

`qota/phones.py` provides the ISO region catalog (`phonenumbers` / `pycountry`
with `Babel` localized names), ASCII national number validation, per-region
validity, E.164 formatting, and round-trip verification. It accepts fixed and
mobile numbers and preserves significant leading zeros.

`Subscriber` uses `primary_phone` as its single editable national number and
stores `primary_phone_region` (length 2) and `primary_phone_e164` (`Data`,
length 16, `read_only`). There is no second national field in its metadata.
The original number is never rewritten on validation, form load, or region
assignment; only explicit editing changes it. `before_validate` validates any
present telephone on every ordinary save, including unchanged historical
records. Without a region or with an invalid number, save is rejected until
corrected or explicitly cleared; an empty telephone remains optional. E.164 is
always recalculated server-side. Quick Entry is disabled on `Subscriber` so
every creation uses the full form and backend validation.

`default_phone_region` on `Institutional Settings` starts empty and only
preloads the region on new captures via `qota/public/js/phone_capture.js`. The
controlled historical region assignment in
`qota/governance/phone_region_assignment.py` requires System Manager, read and
write permissions on `Institutional Settings` and `Subscriber`, a saved
default region, a 10-minute preview token, and explicit confirmation. It
assigns only missing regions without invoking `Subscriber.save` or altering
phone numbers, preserves invalid historical numbers for later correction, and
records counts, actor, date, and region in `Version`.

`qota/setup.py` (`ensure_navigation` and `_save_navigation`) ensures the
Governance Settings link on the `Subscribers` sidebar and the `Governance`
dock title on install and migrate without exporting site layouts to source.

## Data fixes and historical migrations

A correction that changes billing or contract data is a Frappe patch in
`qota/patches/` and `qota/patches.txt`. Do not apply that correction by a
one-off SQL update. Do not run `bench migrate` unless the task is the
migration.

`qota/patches.txt` lists seven versioned business migrations:
- `v16_9_0_collapse_suspension_reason` in `[pre_model_sync]`
- `v16_7_0_fix_monthly_bill_status_from_debt_ledger` in `[post_model_sync]`
- `v16_9_0_backfill_reconnection_service_contract` in `[post_model_sync]`
- `v16_9_0_backfill_connection_bill_status` in `[post_model_sync]`
- `v16_9_0_backfill_service_reconnection_status` in `[post_model_sync]`
- `v16_9_0_release_monthly_advances_applied_to_other_charges` in `[post_model_sync]`
- `v16_9_0_record_refinanced_debts` in `[post_model_sync]`

Each patch checks its original unversioned identity first through
`qota.migration_identity.historical_completion`. A clean historical completion
recorded by Frappe skips re-executing the body; a skipped failure without a
later clean retry, an inconsistent traceback, duplicate completions, or an
incomplete log stops migration with `PatchError`. `never_skip_patches` in
`qota/hooks.py` prevents financial migrations from being skipped with
`--skip-failing`.
