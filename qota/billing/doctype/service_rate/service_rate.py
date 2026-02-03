# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

class ServiceRate(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from qota.billing.doctype.service_rate_additional_fee.service_rate_additional_fee import ServiceRateAdditionalFee
        from qota.billing.doctype.service_rate_consumption_range.service_rate_consumption_range import ServiceRateConsumptionRange

        additional_fees: DF.Table[ServiceRateAdditionalFee]
        amended_from: DF.Link | None
        cistern_fee: DF.Currency
        effective_from: DF.Date
        fixed_charge: DF.Currency
        flat_rate_price: DF.Currency
        min_consumption: DF.Float
        ranges: DF.Table[ServiceRateConsumptionRange]
        rate_name: DF.Data
        service_category: DF.Link
        status: DF.Literal["Active", "Inactive"]
    # end: auto-generated types

    def validate(self):
        self.validate_positive_values()
        self.validate_ranges()
        self.check_unique_active_rate()

    def validate_positive_values(self):
        if flt(self.fixed_charge) < 0 or flt(self.flat_rate_price) < 0:
            frappe.throw(_("Price values cannot be negative."))

    def validate_ranges(self):
        """Valida la tabla de rangos de consumo usando tus campos (units)"""
        if not self.ranges:
            return

        # Iniciamos la validación desde el consumo mínimo incluido
        last_to_unit = flt(self.min_consumption)
        
        for d in self.ranges:
            # 1. Validar precio (price_per_unit)
            if flt(d.price_per_unit) < 0:
                frappe.throw(_("Row {0}: Price per unit cannot be negative.").format(d.idx))

            # 2. Validar consistencia interna del rango (to > from)
            # Usamos 'to_unit' y 'from_unit'
            if d.to_unit and flt(d.to_unit) <= flt(d.from_unit):
                frappe.throw(_("Row {0}: 'To' unit must be greater than 'From' unit.").format(d.idx))
            
            # 3. Validar continuidad (que este rango empiece donde terminó el anterior)
            if flt(d.from_unit) < last_to_unit:
                frappe.throw(_("Row {0}: 'From' unit cannot be less than the previous limit ({1}).")
                             .format(d.idx, last_to_unit))
            
            # Si to_unit es 0 o vacío, asumimos infinito
            last_to_unit = flt(d.to_unit) if d.to_unit else 9999999

    def check_unique_active_rate(self):
        """
        Asegura que solo haya una Tarifa Activa por Categoría.
        """
        if self.status == "Active":
            existing = frappe.db.exists("Service Rate", {
                "service_category": self.service_category,
                "effective_from": ["=", self.effective_from],
                "status": "Active",
                "docstatus": ["<", 2], # Excluye cancelados
                "name": ["!=", self.name]
            })
            if existing:
                frappe.throw(_("There is already an active Rate ({0}) for Category '{1}'. Please deactivate it first.")
                             .format(existing, self.service_category))

# --- FUNCIÓN PARA PAYMENT RECEIPT ---
@frappe.whitelist()
def get_estimated_monthly_cost(contract_id):
    """
    Calcula el costo mensual estimado (Base + Fees) para un contrato.
    """
    contract = frappe.db.get_value("Service Contract", contract_id, 
        ["service_category", "billing_basis", "has_cistern"], as_dict=True)
    
    if not contract:
        return 0.0

    rate_name = frappe.db.get_value("Service Rate", 
        {"service_category": contract.service_category, "status": "Active"}, 
        "name"
    )

    if not rate_name:
        return 0.0

    rate = frappe.get_doc("Service Rate", rate_name)
    estimated_total = 0.0

    # A. Calcular Base
    if contract.billing_basis == "Flat Rate":
        estimated_total += flt(rate.flat_rate_price)
        if contract.has_cistern:
            estimated_total += flt(rate.cistern_fee)
    else:
        # En medido, el estimado mínimo es el cargo fijo
        estimated_total += flt(rate.fixed_charge)

    # B. Sumar Fees Adicionales
    if rate.additional_fees:
        for fee in rate.additional_fees:
            estimated_total += flt(fee.amount)

    return estimated_total