# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class BillingSettings(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        apply_isv: DF.Check
        apply_late_fee: DF.Check
        bill_footer_message: DF.TextEditor | None
        company_name: DF.Data
        connection_debt_deadline_days: DF.Int
        cycle_start_day: DF.Int
        days_until_due: DF.Int
        default_currency: DF.Link
        grace_period: DF.Int
        isv_percent: DF.Percent
        late_fee_type: DF.Literal["Fixed Amount", "Percentage"]
        late_fee_value: DF.Currency
        max_discounts_per_connection: DF.Int
        max_discounts_per_subscriber: DF.Int
        min_debt_for_suspension: DF.Currency
        reading_window_days: DF.Int
        reconnection_fee_item: DF.Currency
        separate_cistern_fee: DF.Check
        show_debt_details: DF.Check
        suspension_months_limit: DF.Int
        truncate_discount_decimals: DF.Check
        water_service_label: DF.Data
    # end: auto-generated types

    def validate(self):
        self.validate_cycle_day()
        self.validate_percents()

    def validate_cycle_day(self):
        """Asegura que el día de inicio del ciclo sea válido (1-28 para evitar problemas con febrero)"""
        if self.cycle_start_day < 1 or self.cycle_start_day > 28:
            frappe.throw(_("Cycle Start Day must be between 1 and 28 to ensure compatibility with all months."))

    def validate_percents(self):
        """Valida que los porcentajes no sean ilógicos"""
        if self.apply_isv and (self.isv_percent < 0 or self.isv_percent > 100):
            frappe.throw(_("Tax Percentage must be between 0 and 100."))
            
        if self.apply_late_fee and self.late_fee_type == "Percentage":
            if self.late_fee_value < 0 or self.late_fee_value > 100:
                frappe.throw(_("Late Fee Percentage must be between 0 and 100."))
