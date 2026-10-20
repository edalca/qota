# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

from frappe.model.document import Document

import frappe
from frappe import _

from qota.governance.institutional import ConfigurationError, TIMEZONE, local_datetime, validate_configuration
from qota.phones import PhoneError, validate_region


class InstitutionalSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from qota.governance.doctype.institutional_calendar_exception.institutional_calendar_exception import InstitutionalCalendarException
		from qota.governance.doctype.institutional_exception_hours.institutional_exception_hours import InstitutionalExceptionHours
		from qota.governance.doctype.institutional_office_location.institutional_office_location import InstitutionalOfficeLocation
		from qota.governance.doctype.institutional_weekly_hours.institutional_weekly_hours import InstitutionalWeeklyHours

		calendar_exceptions: DF.Table[InstitutionalCalendarException]
		default_phone_region: DF.Literal[None]
		exception_hours: DF.Table[InstitutionalExceptionHours]
		office_locations: DF.Table[InstitutionalOfficeLocation]
		weekly_hours: DF.Table[InstitutionalWeeklyHours]
	# end: auto-generated types

	def validate(self):
		if frappe.session.user == "Guest" or "System Manager" not in frappe.get_roles():
			frappe.throw(_("Only System Manager can administer institutional settings."), frappe.PermissionError)
		for permission in ("read", "write"):
			if not frappe.has_permission("Institutional Settings", permission, doc=self):
				frappe.throw(_("Only System Manager can administer institutional settings."), frappe.PermissionError)
		try:
			if self.default_phone_region:
				validate_region(self.default_phone_region)
			validate_configuration(self)
		except PhoneError:
			frappe.throw(_("Choose a supported telephone region."))
		except ConfigurationError as exc:
			frappe.throw(_(str(exc)))


@frappe.whitelist(methods=["GET"])
def calendar_context():
	"""Administrative calendar date from the common institutional clock."""
	if frappe.session.user == "Guest" or "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only System Manager can administer institutional settings."), frappe.PermissionError)
	frappe.get_doc("Institutional Settings").check_permission("read")
	return {"today": local_datetime().date().isoformat(), "timezone": TIMEZONE}
