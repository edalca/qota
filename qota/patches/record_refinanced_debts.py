import frappe
from frappe.model.naming import set_new_name
from frappe.utils import flt


def execute():
	"""
	Record the debts each existing refinancing cancelled, and turn off the
	unused automatic late fee. Overdue months are not surcharged.
	"""
	frappe.db.set_single_value("Billing Settings", "apply_late_fee", 0)

	refinancings = frappe.get_all(
		"Debt Refinancing",
		filters={"docstatus": 1},
		fields=["name", "service_contract", "modified"],
	)
	recorded = 0
	for refinancing in refinancings:
		if frappe.db.exists("Refinancing Settled Debt", {"parent": refinancing.name}):
			continue
		recorded += _record(refinancing)

	frappe.db.commit()
	frappe.logger().info(f"record_refinanced_debts: recorded {recorded} settled debts")


def _record(refinancing):
	rows = frappe.db.sql(
		"""
		SELECT
			dle.name,
			dle.entry_type,
			dle.billing_period,
			dle.paid_amount,
			dle.reference_doctype,
			dle.reference_name,
			COALESCE(SUM(CASE WHEN pr.name IS NULL THEN 0 ELSE pri.amount - pri.balance END), 0) AS applied
		FROM `tabDebt Ledger Entry` dle
		LEFT JOIN `tabPayment Receipt Item` pri
			ON pri.debt_ledger_entry = dle.name
		LEFT JOIN `tabPayment Receipt` pr
			ON pr.name = pri.parent AND pr.docstatus = 1
		WHERE dle.service_contract = %s
		  AND dle.creation <= %s
		  AND dle.docstatus != 2
		  AND dle.entry_type NOT IN ('Refinancing Down Payment', 'Refinancing Installment')
		GROUP BY
			dle.name,
			dle.entry_type,
			dle.billing_period,
			dle.paid_amount,
			dle.reference_doctype,
			dle.reference_name
		""",
		(refinancing.service_contract, refinancing.modified),
		as_dict=True,
	)

	idx = 1
	count = 0
	for debt in rows:
		settled = flt(debt.paid_amount) - flt(debt.applied)
		if settled <= 0.01:
			continue
		row = frappe.new_doc("Refinancing Settled Debt")
		row.parent = refinancing.name
		row.parentfield = "settled_debts"
		row.parenttype = "Debt Refinancing"
		row.idx = idx
		row.debt_ledger_entry = debt.name
		row.entry_type = debt.entry_type
		row.billing_period = debt.billing_period
		row.settled_amount = settled
		row.reference_doctype = debt.reference_doctype
		row.reference_name = debt.reference_name
		set_new_name(row)
		row.db_insert()
		idx += 1
		count += 1
	return count
