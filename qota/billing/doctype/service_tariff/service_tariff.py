# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

class ServiceTariff(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from qota.billing.doctype.service_tariff_additional_fee.service_tariff_additional_fee import ServiceTariffAdditionalFee
        from qota.billing.doctype.service_tariff_range.service_tariff_range import ServiceTariffRange

        additional_fees: DF.Table[ServiceTariffAdditionalFee]
        amended_from: DF.Link | None
        cistern_fee: DF.Currency
        effective_from: DF.Date
        fixed_charge: DF.Currency
        flat_rate_price: DF.Currency
        min_consumption: DF.Float
        ranges: DF.Table[ServiceTariffRange]
        service_category: DF.Link
        status: DF.Literal["Active", "Inactive"]
        tariff_name: DF.Data
    # end: auto-generated types

    def validate(self):
        self.validate_positive_values()
        self.validate_ranges()
        self.check_unique_active_tariff()

    def validate_positive_values(self):
        if flt(self.fixed_charge) < 0 or flt(self.flat_rate_price) < 0:
            frappe.throw(_("Price values cannot be negative."))

    def validate_ranges(self):
        """Valida la tabla Service Tariff Range"""
        if not self.ranges:
            return

        last_to_unit = flt(self.min_consumption)
        
        for d in self.ranges:
            # Validar precio del rango
            if flt(d.price_per_unit) < 0:
                frappe.throw(_("Row {0}: Price per m3 cannot be negative.").format(d.idx))

            # Validar lógica de unidades
            if d.to_unit and flt(d.to_unit) <= flt(d.from_unit):
                frappe.throw(_("Row {0}: 'To' unit must be greater than 'From' unit.").format(d.idx))
            
            if flt(d.from_unit) < last_to_unit:
                frappe.throw(_("Row {0}: 'From' unit cannot be less than the previous 'To' unit ({1}).")
                             .format(d.idx, last_to_unit))
            
            # Si to_unit es 0 o None, se asume infinito, pero guardamos el valor para la siguiente iteración
            last_to_unit = flt(d.to_unit) if d.to_unit else 9999999

    def check_unique_active_tariff(self):
        if self.status == "Active":
            existing = frappe.db.exists("Service Tariff", {
                "service_category": self.service_category,
                "status": "Active",
                "docstatus": ["<", 2],
                "name": ["!=", self.name]
            })
            if existing:
                frappe.throw(_("There is already an active tariff ({0}) for Category '{1}'.")
                             .format(existing, self.service_type))