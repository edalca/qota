import frappe
from frappe.utils import flt


def execute():
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
			item.amount AS item_amount,
			item.balance AS item_balance,
			item.billing_period,
			parent.service_contract,
			dle.name AS dle_name,
			dle.amount AS dle_amount,
			dle.paid_amount,
			dle.reference_doctype,
			dle.reference_name
		FROM `tabPayment Receipt Item` item
		INNER JOIN `tabPayment Receipt` parent ON parent.name = item.parent
		INNER JOIN `tabDebt Ledger Entry` dle ON dle.name = item.debt_ledger_entry
		WHERE parent.docstatus = 1
		  AND item.payment_concept = 'Monthly Fee'
		  AND dle.entry_type != 'Monthly Fee'
		  AND dle.docstatus != 2
		""",
		as_dict=True,
	)

	if not rows:
		return

	for row in rows:
		applied = max(flt(row.item_amount) - flt(row.item_balance), 0)
		paid = max(flt(row.paid_amount) - applied, 0)
		outstanding = flt(row.dle_amount) - paid
		if outstanding <= 0.01:
			status = "Paid"
		elif paid > 0:
			status = "Partially Paid"
		else:
			status = "Unpaid"

		frappe.db.set_value(
			"Debt Ledger Entry",
			row.dle_name,
			{
				"paid_amount": paid,
				"outstanding_amount": outstanding,
				"status": status,
			},
			update_modified=False,
		)
		if status != "Paid":
			_reopen_reference_if_paid(row.reference_doctype, row.reference_name)

		frappe.db.set_value(
			"Payment Receipt Item",
			row.item_name,
			{"balance": flt(row.item_amount), "debt_ledger_entry": None},
			update_modified=False,
		)
		_apply_to_monthly_fee(row.service_contract, row.billing_period)

	frappe.db.commit()
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

	monthly = frappe.db.get_value(
		"Debt Ledger Entry",
		{
			"service_contract": service_contract,
			"billing_period": billing_period,
			"entry_type": "Monthly Fee",
			"docstatus": ["!=", 2],
			"outstanding_amount": [">", 0.01],
		},
		"name",
	)
	if not monthly:
		return

	frappe.get_doc("Debt Ledger Entry", monthly).apply_advance_payments()
