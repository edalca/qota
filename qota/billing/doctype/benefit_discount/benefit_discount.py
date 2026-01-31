# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class BenefitDiscount(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amended_from: DF.Link | None
		discount_percentage: DF.Percent
		discount_rule: DF.Link
		effective_date: DF.Date
		full_name: DF.Data | None
		premises: DF.Link | None
		service_contract: DF.Link
		status: DF.Literal["Active", "Inactive"]
	# end: auto-generated types

	pass
