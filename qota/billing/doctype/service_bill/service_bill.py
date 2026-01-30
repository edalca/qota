# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from qota.billing.doctype.billing_entry.billing_entry import make_billing_entry

class ServiceBill(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amended_from: DF.Link | None
        billing_entry: DF.Link | None
        billing_month: DF.Literal["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        billing_year: DF.Link
        contract: DF.Link
        full_name: DF.Data | None
        posting_date: DF.Date
        premises: DF.Link | None
        subscriber: DF.Link | None
        total_amount: DF.Currency
    # end: auto-generated types

    def on_submit(self):
        """Generates a manual Billing Entry upon submission"""

        # 1. Ejecutar el motor centralizado
        bill = make_billing_entry(
            contract=self.contract,
            month=self.billing_month,
            year=self.billing_year,
            posting_date=self.posting_date,
            source_type="Service Bill",
            source_name=self.name
        )

        if bill:
            # 2. Guardar la referencia de lo generado para que el usuario pueda verlo
            self.billing_entry = bill.name
            self.total_amount = bill.total_amount
            self.db_update()
        else:
            # Si make_billing_entry devolvió None (por duplicado), lanzamos error
            frappe.throw(frappe._("A Billing Entry already exists for this contract and period."))

    def on_cancel(self):
        """Handle cancellation of the Service Bill and its entry"""
        if self.billing_entry:
            # Buscamos el entry generado
            entry = frappe.get_doc("Billing Entry", self.billing_entry)
            
            # Solo permitimos cancelar si no está pagado aún
            if entry.status == "Paid":
                frappe.throw(frappe._("Cannot cancel this bill because it has already been paid."))
                
            entry.docstatus = 2  # Marcar como cancelado (Cancelled)
            entry.save(ignore_permissions=True)