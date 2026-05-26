import frappe
from frappe.utils import flt


def execute():
	"""
	Backfill status on Service Reconnection records with missing or incorrect values.

	- "Unpaid" / "Partially Paid" → "Unpaid"  (pushed by old sync_reference_document_status)
	- docstatus=1, fee=0, not Executed → "Paid"
	- docstatus=1, fee>0, DLE paid → "Paid"
	- docstatus=1, fee>0, DLE outstanding → "Unpaid"
	- docstatus=2 → "Cancelled"
	- "Executed" → keep as-is
	"""
	records = frappe.get_all(
		"Service Reconnection",
		fields=["name", "docstatus", "status", "reconnection_fee"],
	)

	if not records:
		return

	# Build map of paid DLEs referenced by Service Reconnection
	paid_refs = set(
		frappe.db.sql_list("""
			SELECT reference_name
			FROM `tabDebt Ledger Entry`
			WHERE reference_doctype = 'Service Reconnection'
			  AND status = 'Paid'
			  AND docstatus != 2
		""")
	)

	valid_statuses = {"Draft", "Unpaid", "Paid", "Scheduled", "Executed", "Cancelled"}

	updated = 0
	for rec in records:
		if rec.docstatus == 2:
			new_status = "Cancelled"
		elif rec.status == "Executed":
			continue
		elif rec.status in valid_statuses and rec.status not in ("Unpaid", "Partially Paid"):
			continue
		elif flt(rec.reconnection_fee) == 0:
			new_status = "Paid"
		elif rec.name in paid_refs:
			new_status = "Paid"
		else:
			new_status = "Unpaid"

		frappe.db.set_value(
			"Service Reconnection", rec.name, "status", new_status, update_modified=False
		)
		updated += 1

	frappe.db.commit()
	frappe.logger().info(f"backfill_service_reconnection_status: updated {updated} records")
