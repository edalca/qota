# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ConnectionTariff(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        description: DF.SmallText | None
        disabled: DF.Check
        max_installments: DF.Int
        min_down_payment: DF.Currency
        tariff_name: DF.Data
        total_fee: DF.Currency
    # end: auto-generated types

    def validate(self):
        self.validate_values()
        self.check_unique_active_tariff()

    def validate_values(self):
        if self.total_fee <= 0:
            frappe.throw(_("The total connection fee must be greater than zero."))
        
        if self.min_down_payment > self.total_fee:
            frappe.throw(_("The minimum down payment cannot be greater than the total fee."))
            
        if self.max_installments < 1:
            frappe.throw(_("Maximum installments must be at least 1."))

    def check_unique_active_tariff(self):
        if not self.disabled:
            existing_active = frappe.db.exists("Connection Tariff", {
                "disabled": 0,
                "name": ["!=", self.name]
            })
            if existing_active:
                frappe.throw(_("There is already an active tariff ({0}).").format(existing_active))
