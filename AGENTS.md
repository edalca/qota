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

Production is a separate site. This tree is not deployed there by editing
files here.

## Modules

`qota/modules.txt` lists three modules, in this order:

- `Governance` holds subscribers, premises, contracts, suspensions, and
  reconnections.
- `Billing` holds charges, receipts, refinancing, rates, billing setup, and
  the WhatsApp notice settings.
- `Expenditures` holds expense vouchers and categories.

The WhatsApp protocol module belongs to the official Frappe app
`whatsapp`, not to Qota. A DocType stays in the module that owns its files
under `qota/<module>/doctype/`. Menu changes do not move DocTypes between
modules.

## Desk navigation

Frappe 16.50 and later splits navigation into three steps:

1. Desktop shows one icon per app. Qota is registered in
   `add_to_apps_screen` in `qota/hooks.py`. The `name` must be the app name
   `qota`. A display title such as `Qota` does not attach the dock.
2. The dock is the narrow column of sidebar icons. The shipped dock is
   `qota/dock/qota/qota.json`, in this order: Collection, Billing,
   Subscribers, Expenditures, WhatsApp. Opening the app lands on Collection.
3. A module keeps the sidebar titled with its name, because that is the
   sidebar the desk uses for the module. A module may also own extra
   sidebars. Each sidebar has its own desk URL, so a refresh stays on that
   sidebar. DocTypes stay in their modules.

The apps screen hides the dock. The dock appears after the app icon is
opened. `Desktop Settings` → `Desktop Page` = `Apps` is the new home. `Desktop
Icons` is the old grid.

The four dock sidebars, with the icon from `qota/public/icons/icons.svg`:

- `Collection` (Cobro), module Billing, icon `collection-cash-duotone`.
  The glyph is an old cash register: a square body and a small display.
  The drawer slides open on hover. Opens on Payment Receipt. Items: Payment Receipt, Debt Refinancing, then
  Reports (Daily Collection, Customer Statement, Advance Payments,
  Advances and Surplus). File:
  `qota/billing/sidebar/collection/collection.json`.
- `Subscribers` (Abonados), module Governance, icon
  `subscribers-card-duotone`. Opens on Subscriber. Items: Subscriber,
  Premises, Service Contract, then Operations (Service Suspension, Service
  Reconnection), then Reports (Delinquent Subscribers, Service
  Suspensions). File:
  `qota/governance/sidebar/subscribers/subscribers.json`.
- `Billing` (Facturación), icon `billing-drop-duotone`. Opens on Monthly
  Bill. Items: Monthly Bill, Connection Bill, Meter Reading, Service Fine,
  then Masters (Billing Year, Service Rate, Discount Rule, Benefit
  Discount), then Reports (Aging Report, Billing and Collections), then
  Settings (Billing Cycle, Billing Settings).
- `Expenditures` (Gastos), icon `expenditures-coin-duotone`. Opens on
  Expense Voucher. Items: Expense Voucher, Expense Category.
- `WhatsApp`, icon `whatsapp-chat-duotone`. Opens on Conversations.
  The shell is the official WhatsApp module. Qota writes that sidebar from
  `qota.whatsapp_desk.ensure_whatsapp_desk` because the official app
  ships no desk menu and its files are not edited. Items: Conversations,
  WhatsApp Notifications, then the official WA Account, WA Settings,
  WA Message, WA Profile, WA Template, and WA Log.

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

`qota/workspace_sidebar/` is the old sidebar format. Frappe 16.50 does not
read it. Do not treat it as the current menu.

A pinned dock stays visible. A floating dock stays off-screen until the
pointer touches the left edge.

## Billing

Charges are Debt Ledger Entry documents. The customer statement debits every
ledger amount and credits every submitted Payment Receipt Item amount, plus
one credit per submitted Debt Refinancing equal to its current total debt.
The running balance is debits minus credits. A prepaid position can be
negative while some ledger rows still show an outstanding amount.

A Monthly Fee advance covers a monthly charge only when the receipt item
concept is Monthly Fee and the billing period matches. Apply unused advance
to the oldest matching period first. The item `balance` is the unused
advance. The receipt header `unallocated_amount` can be stale.

Service Fine, on submit, creates only a Service Fine ledger entry. It does
not create a Service Suspension.

Do not reintroduce Refinancing Credit ledger entries. Debt Refinancing is
recorded by `qota.patches.record_refinanced_debts`.

Delinquent Subscribers counts a month only when its due date plus grace is
before today and unused Monthly Fee advance does not cover it, oldest first.
Net outstanding may be negative. Rows with net at or under 0.01, or with
fewer uncovered periods than the minimum, are excluded.

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

## WhatsApp

The official Frappe app `whatsapp` (branch `develop`) owns the Cloud API:
WA Account, WA Settings, WA Template, WA Message, WA Profile, and WA Log.
Its webhook is `whatsapp.whatsapp.webhook.handler`. Qota does not edit that
app. Document events live in `qota/events` (`whatsapp_notices`). Desk
methods live in `qota/apis` (`whatsapp_inbox`). The sidebar builder is
`qota/whatsapp_desk`, called from `after_migrate`. `qota/overrides` is only
for replacing the Python controller of a DocType that belongs to another
app. Qota keeps the dock, the Conversations page, and the two junta notices.
The notice settings single stays in Billing.

Notices are outbound utility templates. A failed send is logged on WA
Message and does not undo the document. The connection lives on WA Account
and WA Settings. Which notices go out, and the template names, live on the
Qota single WhatsApp Notifications in Billing.

WA Account is extended from `qota/setup.py`. `qota.install.after_migrate`
runs that setup on `bench migrate`, including a production migrate.
`after_install` runs it on a new site. `before_uninstall` removes the
fields and the list settings. The official DocType is not edited.
`qota_abbreviation` is required and holds at most 10 letters.
`qota_phone_number` is the telephone number. `phone_id` stays the Meta phone
number id. The account list shows the junta name, the abbreviation, the
phone number, and the status.

The junta templates are composed in code. `send_template` cannot fill them,
because that API reads every variable from one reference document. Qota
inserts a WA Message with `template_body_parameters` already set and submits
it. The local WA Template rows for `qota_payment_received` and
`qota_service_suspension` stay without a reference DocType, so submit does
not replace those parameters. Header and footer stay fixed.

Inbound messages arrive through the official webhook. A person does not
have to be a subscriber. The thread is the WA Profile for that phone. A
matching subscriber phone is linked on the profile. The desk page is
Conversations, under Billing, and it reads WA Profile and WA Message.

`qota/hooks.py` enqueues a payment notice on Payment Receipt submit and a
scheduled suspension notice on Service Suspension submit. The executed
notice is not a hook. `execute_suspension_logic` enqueues it after save.
The same WA Message row is the conversation entry for that phone.

One suspension template covers both phases. The stored body names are
`name`, `suspension`, `contract`, and `message`. The scheduled message uses
the effective date. The executed message uses `executed_date`. When those
dates differ, the message appends the programmed date. Idempotency is per
phase, using the preview prefix `[Scheduled]` or `[Executed]`.

The payment template body names are `receipt`, `name`, `contract`, `date`,
`detail`, and `amount`. Detail lines are joined with ` ‖ ` (U+2016). Header
and footer are fixed text. Qota does not send header or footer parameters.
Template variables must stay in named mode. A body must not start or end on
a variable, and a parameter cannot contain a line break. The names above stay
as they are.

Every notice uses the same order, tone, spacing, bold, and closing. A notice
includes only the data that belongs to it.

1. The header names the kind of notice.
2. The greeting is `Hola *{{name}}*.`
3. The introduction names the Junta Administradora de Agua and states the event.
4. The reference puts identifiers and dates in that first paragraph.
5. The detail is a bold title with a colon, then the dynamic text.
6. The result adds an amount or another outcome when the notice has one.
7. The closing points the person to the administration. Only the subject changes.
8. The footer is always `Junta Administradora de Agua · Notificaciones`.

`qota_payment_received`. Header: `Confirmación de Pago Recibido`.

```text
Hola *{{name}}*.

La Junta Administradora de Agua te confirma que se ha registrado el pago identificado con el recibo {{receipt}}, correspondiente al contrato {{contract}}, con fecha {{date}}.

*Detalle del pago:*
{{detail}}

Total recibido: {{amount}}

Para consultas o aclaraciones sobre este pago, comunícate con nuestra administración.
```

`qota_service_suspension`. Header: `Aviso de Suspensión del Servicio`.

```text
Hola *{{name}}*.

La Junta Administradora de Agua te notifica que se ha emitido el aviso de suspensión {{suspension}}, correspondiente al contrato {{contract}}.

*Detalle de la notificación:*
{{message}}

Para consultas o aclaraciones sobre este aviso, comunícate con nuestra administración.
```

Do not print or store access tokens in this file, in notes, or in chat.

## Data fixes

A correction that changes billing or contract data is a Frappe patch in
`qota/patches/` and `qota/patches.txt`. Do not apply that correction by a
one-off SQL update. Do not run `bench migrate` unless the task is the
migration.

## Not built

Production is not updated by this checkout. The official WhatsApp app is
installed on the local site only. The webhook on production is reached only
after that app and this checkout are deployed there and the callback URL on
that site is a public address Meta can call.
