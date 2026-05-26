import frappe


def execute():
	"""
	Backfill service_contract on Service Reconnection records created before
	the field existed. Derives the value from the linked Service Suspension.
	"""
	records = frappe.get_all(
		"Service Reconnection",
		filters={"service_contract": ["in", ["", None]]},
		fields=["name", "service_suspension"],
	)

	if not records:
		return

	updated = 0
	for rec in records:
		if not rec.service_suspension:
			continue

		service_contract = frappe.db.get_value(
			"Service Suspension", rec.service_suspension, "service_contract"
		)

		if service_contract:
			frappe.db.set_value(
				"Service Reconnection",
				rec.name,
				"service_contract",
				service_contract,
				update_modified=False,
			)
			updated += 1

	frappe.db.commit()
	frappe.logger().info(
		f"backfill_reconnection_service_contract: updated {updated} of {len(records)} records"
	)
