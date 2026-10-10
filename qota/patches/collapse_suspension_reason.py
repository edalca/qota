import frappe


def execute():
	"""Keep one suspension reason: subscriber request, arrears, or fine.

	Older orders stored a type (Administrative / By Request) plus a separate
	reason. The reason column is removed when the DocType is synced, so the
	value has to move first.
	"""
	if not frappe.db.has_column("Service Suspension", "reason"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabService Suspension`
		SET suspension_type = CASE
			WHEN reason IN ('Fraud / Bypass', 'Sanction') THEN 'By Fine'
			WHEN reason = 'Subscriber Request' OR suspension_type = 'By Request'
				THEN 'Subscriber Request'
			WHEN reason = 'Maintenance' THEN 'Subscriber Request'
			ELSE 'Arrears'
		END
		WHERE IFNULL(suspension_type, '') NOT IN ('Subscriber Request', 'Arrears', 'By Fine')
			OR IFNULL(reason, '') != ''
		"""
	)
	frappe.db.commit()
