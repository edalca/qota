# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class BillingYear(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		end_date: DF.Date
		is_closed: DF.Check
		start_date: DF.Date
		year_name: DF.Data
	# end: auto-generated types

	pass
