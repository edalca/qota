# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class PaymentAllocation(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Currency
		debt_ledger_entry: DF.Link
		payment_receipt: DF.Link
		transaction_date: DF.Date
	# end: auto-generated types

	pass
