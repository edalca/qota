# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today

class DebtLedgerEntry(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amount: DF.Currency
        entry_type: DF.Literal["Connection Fee", "Monthly Fee", "Late Fee", "Payment", "Reconnection Fee"]
        fiscal_month: DF.Literal["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        fiscal_year: DF.Int
        full_name: DF.Data | None
        posting_date: DF.Date
        premises: DF.Link | None
        reference_doctype: DF.Link | None
        reference_name: DF.DynamicLink | None
        service_contract: DF.Link
        subscriber: DF.Link | None
    # end: auto-generated types

    @staticmethod
    def create_entry(contract, entry_type, amount, ref_dt, ref_dn, posting_date=None, fiscal_year=None, fiscal_month=None,description=None):
        """
        Método centralizado para registrar deudas o pagos en el historial del contrato.
        
        Args:
            contract (str): ID del Service Contract.
            entry_type (str): Tipo de movimiento (Connection Fee, Monthly Bill, Payment...).
            amount (float): Monto (Positivo = Deuda, Negativo = Abono).
            ref_dt (str): DocType de origen (ej. 'Service Contract', 'Service Bill').
            ref_dn (str): ID del documento origen.
            posting_date (date, optional): Fecha del movimiento. Default: Hoy.
        """
        
        if not amount:
            return

        entry = frappe.new_doc("Debt Ledger Entry")
        entry.posting_date = posting_date or today()
        entry.service_contract = contract
        entry.entry_type = entry_type
        entry.amount = amount
        entry.reference_doctype = ref_dt
        entry.reference_name = ref_dn
        entry.fiscal_year = fiscal_year
        entry.fiscal_month = fiscal_month
        entry.description = description
        
        # Insertar ignorando permisos (porque es un proceso del sistema)
        entry.insert(ignore_permissions=True)
        
        return entry.name