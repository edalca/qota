# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from qota.billing.doctype.debt_ledger_entry.debt_ledger_entry import (
	clear_and_delete_debt,
	make_debt_ledger_entry,
)


class ServiceFine(Document):
	def validate(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("The fine amount must be greater than zero."))

	def on_submit(self):
		self.db_set("status", "Unpaid")
		make_debt_ledger_entry(
			contract_name=self.service_contract,
			entry_type="Service Fine",
			amount=flt(self.amount),
			ref_dt=self.doctype,
			ref_dn=self.name,
			description=self.description or _("Service fine {0}: misuse of water.").format(self.name),
			reference_date=str(self.posting_date),
			skip_duplicate_check=True,
		)

	def on_cancel(self):
		linked = frappe.db.get_value(
			"Service Suspension",
			{"service_fine": self.name, "docstatus": ["<", 2]},
			"name",
		)
		if linked:
			frappe.throw(
				_("Cancel Service Suspension {0} before cancelling this fine.").format(linked)
			)
		clear_and_delete_debt(self.doctype, self.name)
		self.db_set("status", "Cancelled")
