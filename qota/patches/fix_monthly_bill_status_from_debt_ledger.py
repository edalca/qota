import frappe
from frappe.utils import flt


def execute():
	"""
	Sync Monthly Bill status from its Debt Ledger Entry for records that were created
	before sync_reference_document_status was in place.
	"""
	stale_bills = frappe.get_all(
		"Monthly Bill",
		filters={"status": ["in", ["Unpaid", "Partially Paid"]], "docstatus": 1},
		fields=["name"],
		pluck="name",
	)

	if not stale_bills:
		return

	debt_entries = frappe.get_all(
		"Debt Ledger Entry",
		filters={
			"reference_doctype": "Monthly Bill",
			"reference_name": ["in", stale_bills],
			"docstatus": 1,
		},
		fields=["reference_name", "status", "outstanding_amount"],
	)

	updated = 0
	for dle in debt_entries:
		if flt(dle.outstanding_amount) <= 0.01:
			correct_status = "Paid"
		elif dle.status == "Partially Paid":
			correct_status = "Partially Paid"
		else:
			continue

		frappe.db.set_value("Monthly Bill", dle.reference_name, "status", correct_status, update_modified=False)
		updated += 1

	frappe.db.commit()
	frappe.logger().info(f"fix_monthly_bill_status: updated {updated} of {len(stale_bills)} stale bills")
