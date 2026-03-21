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


class ConnectionBill(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amended_from: DF.Link | None
		amount: DF.Currency
		description: DF.SmallText | None
		full_name: DF.Data | None
		posting_date: DF.Date
		premises: DF.Link | None
		service_category: DF.Link | None
		service_contract: DF.Link
		subscriber: DF.Link | None
	# end: auto-generated types

	def validate(self):
		self.fetch_service_category()
		self.apply_default_amount()
		self.check_no_duplicate()

	def on_submit(self):
		self.create_debt_ledger_entry()

	def on_cancel(self):
		self.remove_debt_ledger_entry()

	def fetch_service_category(self):
		"""Set service_category from the linked Service Contract."""
		self.service_category = frappe.db.get_value(
			"Service Contract", self.service_contract, "service_category"
		)

	def apply_default_amount(self):
		"""Set amount from Billing Settings default if not already provided."""
		if not flt(self.amount):
			self.amount = flt(frappe.db.get_single_value("Billing Settings", "default_connection_fee"))

	def check_no_duplicate(self):
		"""Raise an error if an active Connection Bill already exists for this contract."""
		existing = frappe.db.exists(
			"Connection Bill",
			{
				"service_contract": self.service_contract,
				"docstatus": ["!=", 2],
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw(
				_("A Connection Bill ({0}) already exists for contract {1}.").format(
					existing, self.service_contract
				)
			)

	def create_debt_ledger_entry(self):
		"""Create a Debt Ledger Entry for the connection fee amount."""
		description = self.description or _("Connection fee for service contract {0}.").format(
			self.service_contract
		)
		make_debt_ledger_entry(
			contract_name=self.service_contract,
			entry_type="Connection Fee",
			amount=self.amount,
			ref_dt="Connection Bill",
			ref_dn=self.name,
			description=description,
		)

	def remove_debt_ledger_entry(self):
		"""Delete the associated Debt Ledger Entry when this charge is cancelled."""
		clear_and_delete_debt("Connection Bill", self.name)
