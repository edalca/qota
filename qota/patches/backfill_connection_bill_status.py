import frappe


def execute():
	"""
	Backfill status on Connection Bill records created before the field existed.
	- docstatus = 0 → Draft
	- docstatus = 1, DLE paid → Paid
	- docstatus = 1, DLE unpaid/partial → Unpaid
	- docstatus = 2 → Cancelled
	"""
	records = frappe.get_all(
		"Connection Bill",
		fields=["name", "docstatus"],
	)

	if not records:
		return

	paid_bills = set(
		frappe.db.sql_list("""
			SELECT reference_name
			FROM `tabDebt Ledger Entry`
			WHERE reference_doctype = 'Connection Bill'
			  AND status = 'Paid'
			  AND docstatus != 2
		""")
	)

	updated = 0
	for rec in records:
		if rec.docstatus == 2:
			status = "Cancelled"
		elif rec.docstatus == 0:
			status = "Draft"
		elif rec.name in paid_bills:
			status = "Paid"
		else:
			status = "Unpaid"

		frappe.db.set_value("Connection Bill", rec.name, "status", status, update_modified=False)
		updated += 1

	frappe.db.commit()
	frappe.logger().info(f"backfill_connection_bill_status: updated {updated} records")
