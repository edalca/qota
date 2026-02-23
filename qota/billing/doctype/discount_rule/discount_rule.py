# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class DiscountRule(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        condition_type: DF.Literal["Age", "Manual Tag", "All Subscribers"]
        description: DF.SmallText | None
        discount_name: DF.Data
        discount_percentage: DF.Percent
        discount_type: DF.Literal["Fixed Amount", "Percentage"]
        fixed_amount: DF.Currency
        is_active: DF.Check
        maximum_age: DF.Int
        minimum_age: DF.Int
        requires_cistern: DF.Literal["Irrelevant", "Yes", "No"]
    # end: auto-generated types

    def validate(self):
        self.validate_discount_value()
        if self.condition_type == "Age":
            self.validate_age_range()

    def validate_discount_value(self):
        """Ensures that the selected discount type has a
        valid positive value."""

        if self.discount_type == "Percentage":
            if (
                flt(self.discount_percentage) <= 0 or
                flt(self.discount_percentage) > 100
            ):
                frappe.throw(_("Discount percentage must be between 1 and 100"))
            # Optional: Clear fixed_amount if type is Percentage
            self.fixed_amount = 0

        elif self.discount_type == "Fixed Amount":
            if flt(self.fixed_amount) <= 0:
                frappe.throw(_("Fixed Amount must be greater than 0"))
            # Optional: Clear percentage if type is Fixed
            self.discount_percentage = 0

    def validate_age_range(self):
        """Validates age boundaries when condition type is Age."""
        if self.minimum_age and self.maximum_age:
            if int(self.minimum_age) >= int(self.maximum_age):
                frappe.throw(_("Minimum Age must be less than Maximum Age"))

        if flt(self.minimum_age) < 0:
            frappe.throw(_("Minimum Age cannot be negative"))
