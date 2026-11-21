import frappe
from qota.migration_identity import historical_completion
from decimal import Decimal
from frappe.modules.patch_handler import PatchError
from frappe.utils import flt


def execute():
	if historical_completion("qota.patches.release_monthly_advances_applied_to_other_charges"):
		return
	_migrate()


def _migrate():
	"""
	Release Monthly Fee advances that were applied to a different charge.

	An advance may only settle the Monthly Fee of that same period. Older
	runs applied it to any debt sharing the billing period, such as the
	connection fee DLE-26-08411.
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			item.name AS item_name,
			CAST(item.amount AS CHAR) AS item_amount,
			CAST(item.balance AS CHAR) AS item_balance,
			item.billing_period,
			parent.service_contract,
			dle.name AS dle_name,
			CAST(dle.amount AS CHAR) AS dle_amount,
			CAST(dle.paid_amount AS CHAR) AS paid_amount,
			CAST(dle.outstanding_amount AS CHAR) AS outstanding_amount,
			dle.service_contract AS ledger_contract,
			dle.reference_doctype,
			dle.reference_name
		FROM `tabPayment Receipt Item` item
		INNER JOIN `tabPayment Receipt` parent ON parent.name = item.parent
		INNER JOIN `tabDebt Ledger Entry` dle ON dle.name = item.debt_ledger_entry
		WHERE parent.docstatus = 1
		  AND item.payment_concept = 'Monthly Fee'
		  AND dle.entry_type != 'Monthly Fee'
		  AND dle.docstatus != 2
		ORDER BY dle.name,item.name FOR UPDATE
		""",
		as_dict=True,
	)

	if not rows:
		return

	# Validate and aggregate the original snapshot once per ledger entry.
	groups = {}
	for row in rows:
		amount, balance = Decimal(str(row.item_amount)), Decimal(str(row.item_balance))
		if amount < 0 or balance < 0 or balance > amount or row.service_contract != row.ledger_contract:
			raise PatchError(f"AdvanceEvidenceInvalid: {row.item_name}")
		group = groups.setdefault(row.dle_name, dict(row=row, released=Decimal(0)))
		group["released"] += amount - balance
	for name, group in groups.items():
		row = group["row"]
		paid, amount = Decimal(str(row.paid_amount)), Decimal(str(row.dle_amount))
		if (paid < group["released"] or paid > amount or paid < 0
			or abs(amount - paid - Decimal(str(row.outstanding_amount))) > Decimal("0.01")):
			raise PatchError(f"AdvanceLedgerMismatch: {name}")
		if frappe.db.exists("Refinancing Settled Debt", {"debt_ledger_entry": name}):
			raise PatchError(f"AdvanceAlreadyRefinanced: {name}")

	for name, group in groups.items():
		row = group["row"]
		paid = Decimal(str(row.paid_amount)) - group["released"]
		outstanding = Decimal(str(row.dle_amount)) - paid
		status = "Paid" if outstanding <= Decimal("0.01") else "Partially Paid" if paid > 0 else "Unpaid"
		frappe.db.set_value("Debt Ledger Entry", name,
			dict(paid_amount=paid, outstanding_amount=outstanding, status=status), update_modified=False)
		if status != "Paid":
			_reopen_reference_if_paid(row.reference_doctype, row.reference_name)
	# Release every wrong allocation before the current monthly allocator sees balances.
	for row in rows:
		frappe.db.set_value("Payment Receipt Item", row.item_name,
			dict(balance=row.item_amount, debt_ledger_entry=None), update_modified=False)
	for contract, period in sorted({(r.service_contract, r.billing_period) for r in rows}, key=str):
		_apply_to_monthly_fee(contract, period)

	frappe.logger().info(
		f"release_monthly_advances_applied_to_other_charges: released {len(rows)} advances"
	)


def _reopen_reference_if_paid(doctype, name):
	"""Return a source document to Unpaid when the wrong advance had marked it Paid."""
	if not doctype or not name or not frappe.db.exists("DocType", doctype):
		return

	meta = frappe.get_meta(doctype)
	status_field = meta.get_field("status")
	if not status_field or "Unpaid" not in (status_field.options or "").split("\n"):
		return
	if frappe.db.get_value(doctype, name, "status") != "Paid":
		return

	frappe.db.set_value(doctype, name, "status", "Unpaid", update_modified=False)


def _apply_to_monthly_fee(service_contract, billing_period):
	"""Settle the released advance against the Monthly Fee of the same period, if it exists."""
	if not service_contract or not billing_period:
		return

	monthly = frappe.get_all(
		"Debt Ledger Entry",
		filters={
			"service_contract": service_contract,
			"billing_period": billing_period,
			"entry_type": "Monthly Fee",
			"docstatus": ["!=", 2],
			"outstanding_amount": [">", 0.01],
		},
		pluck="name",
	)
	if not monthly:
		return

	if len(monthly) != 1:
		raise PatchError("AdvanceMonthlyTargetAmbiguous")
	frappe.get_doc("Debt Ledger Entry", monthly[0]).apply_advance_payments()
