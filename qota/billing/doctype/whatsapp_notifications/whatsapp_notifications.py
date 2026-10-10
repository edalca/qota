# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WhatsAppNotifications(Document):
	def validate(self):
		if self.payment_template:
			self.payment_template = self.payment_template.strip()
		if self.suspension_template:
			self.suspension_template = self.suspension_template.strip()
		if self.notify_on_payment and not self.payment_template:
			frappe.throw(_("The payment template name is required."))
		if self.notify_on_suspension and not self.suspension_template:
			frappe.throw(_("The suspension template name is required."))
