# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class PaymentReceiptItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Currency
		balance: DF.Currency
		billing_details: DF.SmallText | None
		billing_period: DF.Data | None
		debt_ledger_entry: DF.Link | None
		description: DF.Data | None
		due_date: DF.Date | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		payment_concept: DF.Literal["Connection Fee", "Monthly Fee", "Late Fee", "Reconnection Fee"]
	# end: auto-generated types

	pass
