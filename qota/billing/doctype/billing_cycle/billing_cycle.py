import frappe
from frappe import _
from frappe.model.document import Document
from qota.billing.doctype.billing_entry.billing_entry import make_billing_entry

class BillingCycle(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from qota.billing.doctype.billing_cycle_item.billing_cycle_item import BillingCycleItem

        amended_from: DF.Link | None
        generated_entries: DF.Table[BillingCycleItem]
        month: DF.Literal["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        period_end: DF.Date | None
        period_start: DF.Date | None
        posting_date: DF.Date
        total_amount: DF.Currency
        total_entries: DF.Int
        year: DF.Link
    # end: auto-generated types

    def validate(self):
        """Validaciones previas al guardado"""
        # Mapeo de mes para el autoname (si usas month_number)
        month_map = {
            "January": "01", "February": "02", "March": "03", "April": "04",
            "May": "05", "June": "06", "July": "07", "August": "08",
            "September": "09", "October": "10", "November": "11", "December": "12"
        }
        self.month_number = month_map.get(self.month, "00")
        
        self.prevent_duplicate_cycle()

    def on_submit(self):
        """Ejecuta el proceso masivo de facturación"""
        self.process_batch_billing()

    def prevent_duplicate_cycle(self):
        """Evita duplicados para el mismo periodo"""
        duplicate = frappe.db.exists("Billing Cycle", {
            "month": self.month,
            "year": self.year,
            "name": ["!=", self.name],
            "docstatus": ["<", 2] 
        })
        if duplicate:
            frappe.throw(_("A Billing Cycle already exists for {0} {1}").format(self.month, self.year))

    def process_batch_billing(self):
        """Orquestador que recorre los contratos y genera los registros"""
        # 1. Obtenemos todos los contratos activos
        active_contracts = frappe.get_all("Contract", filters={"status": "Active"})
        
        total_billed = 0
        count = 0

        for contract in active_contracts:
            # 2. LLAMADA AL MOTOR CENTRALIZADO
            # Esta función hace los cálculos, aplica descuentos y crea las líneas
            bill = make_billing_entry(
                contract=contract.name,
                month=self.month,
                year=self.year,
                posting_date=self.posting_date,
                source_type="Billing Cycle",
                source_name=self.name
            )
            
            # 3. Si se generó el cobro (no era duplicado), registramos en la tabla hija del ciclo
            if bill:
                self.append("generated_entries", {
                    "contract": contract.name,
                    "billing_entry": bill.name,
                    "amount": bill.total_amount
                })
                total_billed += bill.total_amount
                count += 1
        
        # 4. Actualizamos el resumen del documento maestro
        self.total_entries = count
        self.total_amount	= total_billed
        self.db_update()