# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class DiscountRule(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        condition_type: DF.Literal["Age", "Manual Tag"]
        description: DF.SmallText | None
        discount_name: DF.Data
        discount_percentage: DF.Percent
        maximum_age: DF.Int
        minimum_age: DF.Int
    # end: auto-generated types
    
    def validate(self):
        self.validate_percentage()
        if self.condition_type == "Age":
            self.validate_age_range()

    def validate_percentage(self):
        if self.discount_percentage <= 0 or self.discount_percentage > 100:
            frappe.throw(_("Discount percentage must be between 1 and 100"))

    def validate_age_range(self):
        if self.minimum_age and self.maximum_age:
            if self.minimum_age >= self.maximum_age:
                frappe.throw(_("Minimum Age must be less than Maximum Age"))
