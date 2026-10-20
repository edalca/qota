# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class InstitutionalCalendarException(Document):
	def validate(self):
		# Parent saves validate the whole calendar and write children via db_update.
		frappe.throw(_("Save calendar exceptions through Governance Settings."))

	def on_trash(self):
		frappe.throw(_("Save calendar exceptions through Governance Settings."))
