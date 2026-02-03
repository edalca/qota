# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today, getdate

# Importamos las herramientas centralizadas del archivo utils.py
from qota.billing.utils import allocate_payment_to_debt, get_monthly_billing_breakdown, make_debt_ledger_entry


class PaymentReceipt(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from qota.billing.doctype.payment_receipt_item.payment_receipt_item import PaymentReceiptItem

        advance_items: DF.Table[PaymentReceiptItem]
        amended_from: DF.Link | None
        amount_paid: DF.Currency
        current_debt: DF.Currency
        full_name: DF.Data | None
        mode_of_payment: DF.Literal["Cash", "Bank Transfer", "Check", "Credit Card"]
        payment_date: DF.Datetime
        payment_items: DF.Table[PaymentReceiptItem]
        premises: DF.Link | None
        reference_no: DF.Data | None
        remarks: DF.SmallText | None
        service_contract: DF.Link
        subscriber: DF.Link | None
        total_to_pay: DF.Currency
        unallocated_amount: DF.Currency
    # end: auto-generated types

    def validate(self):
        """
        Este método se ejecuta SIEMPRE al guardar. 
        Asegura que los totales sean correctos independientemente del JavaScript.
        """
        self.calculate_internals()

    def calculate_internals(self):
        total_general = 0
        
        # 1. Sumar de la tabla de deudas pendientes
        for item in self.get("payment_items"):
            total_general += flt(item.amount)
            
        # 2. Sumar de la tabla de adelantos
        for item in self.get("advance_items"):
            total_general += flt(item.amount)
            
        # 3. Asignar valores a los campos del encabezado
        self.total_to_pay = total_general
        self.amount_paid = total_general
        
        # Como el pago es exacto a lo seleccionado, el sobrante es 0
        self.unallocated_amount = 0

    def on_submit(self):
        """
        Applies funds to selected debt entries and calculates the advance balance.
        """
        remaining_funds = flt(self.amount_paid)
        
        # 1. Procesar deudas específicas de la tabla que tienen un vínculo al Ledger
        for item in self.payment_items:
            if remaining_funds <= 0.01:
                break
            
            # Si el item tiene un debt_id, es una deuda existente que debemos cerrar
            if getattr(item, 'debt_id', None):
                current_outstanding = frappe.db.get_value("Debt Ledger Entry", item.debt_id, "outstanding_amount")
                amount_to_apply = min(remaining_funds, flt(current_outstanding))
                
                if amount_to_apply > 0:
                    allocate_payment_to_debt(self.name, item.debt_id, amount_to_apply)
                    remaining_funds -= amount_to_apply
            else:
                # Si no tiene debt_id es un adelanto, restamos del fondo pero no aplicamos a nada
                remaining_funds -= flt(item.amount)

        # 2. El excedente final (o el total de adelantos) se guarda como saldo a favor
        self.db_set("unallocated_amount", remaining_funds if remaining_funds > 0 else 0)

    def on_cancel(self):
        """
        Reverses all ledger allocations and restores debt balances.
        """
        allocations = frappe.get_all("Payment Allocation", 
            filters={"payment_receipt": self.name}, 
            fields=["name", "debt_ledger_entry", "amount"])
        
        for alloc in allocations:
            debt = frappe.get_doc("Debt Ledger Entry", alloc.debt_ledger_entry)
            new_paid = flt(debt.paid_amount) - flt(alloc.amount)
            
            # Restaurar saldos en el Ledger Entry
            debt.db_set("paid_amount", new_paid)
            debt.db_set("outstanding_amount", flt(debt.amount) - new_paid)
            debt.db_set("status", "Unpaid" if new_paid <= 0 else "Partially Paid")
            
            # Eliminar el rastro del vínculo
            frappe.delete_doc("Payment Allocation", alloc.name)

        self.db_set("unallocated_amount", 0)

@frappe.whitelist()
def get_pending_balances(contract):
    """
    Fetches existing debts and determines mandatory status based on due dates.
    """
    debts = frappe.get_all("Debt Ledger Entry",
        filters={
            "service_contract": contract,
            "outstanding_amount": [">", 0],
            "docstatus": 0
        },
        fields=["name as debt_id", "entry_type as payment_concept", "outstanding_amount as amount", "due_date", "description"],
        order_by="creation asc"
    )

    current_date = getdate(today())
    for d in debts:
        # Una deuda es obligatoria si ya pasó su fecha de vencimiento
        is_overdue = True if not d['due_date'] else getdate(d['due_date']) <= current_date
        d['is_mandatory'] = 1 if is_overdue else 0
        d['days_diff'] = frappe.utils.date_diff(d['due_date'], current_date) if d['due_date'] else 0

    return {
        "debts": debts,
        "current_debt": sum(flt(d['amount']) for d in debts)
    }

@frappe.whitelist()
def get_next_billing_advances(contract_name, qty):
    """
    Identifies the last billed period in the system and returns 
    the next N months to be paid as advances.
    """
    from qota.billing.utils import get_monthly_billing_breakdown
    
    contract = frappe.get_doc("Service Contract", contract_name)
    month_names = [
        "January", "February", "March", "April", "May", "June", 
        "July", "August", "September", "October", "November", "December"
    ]

    # --- PASO 1: Buscar el último punto en el historial (Ledger) ---
    last_entry = frappe.get_all("Debt Ledger Entry",
        filters={
            "service_contract": contract_name,
            "entry_type": "Monthly Fee",
            "docstatus": ["!=", 2]
        },
        fields=["reference_name"],
        order_by="creation desc",
        limit=1
    )

    if last_entry and last_entry[0].reference_name:
        # Seguimos la pista: Ledger -> Billing Cycle -> Billing Year
        cycle = frappe.get_doc("Billing Cycle", last_entry[0].reference_name)
        year_val = frappe.db.get_value("Billing Year", cycle.fiscal_year, "year_name")
        
        try:
            last_month = month_names.index(cycle.fiscal_month) + 1
        except ValueError:
            last_month = 1
        last_year = int(year_val)
    else:
        # --- PASO 2: Si no hay historial, aplicar el filtro de seguridad ---
        if not contract.start_date:
            frappe.throw(_("The Service Contract {0} requires a Start Date.").format(contract_name))
        
        contract_start = getdate(contract.start_date)
        
        # Obtener el año abierto más antiguo
        oldest_year_val = frappe.db.get_value("Billing Year", 
            {"is_closed": 0}, "year_name", order_by="year_name asc")
        
        if not oldest_year_val:
            frappe.throw(_("No open Billing Years found in the system."))

        # Convertimos el límite del sistema a fecha
        system_limit_date = getdate(f"{oldest_year_val}-01-01")

        # Elegimos la fecha más reciente (no podemos cobrar antes de que exista el sistema o el contrato)
        actual_start = contract_start if contract_start > system_limit_date else system_limit_date
        
        # Seteamos el puntero justo antes del inicio para que el loop tome el primer mes
        last_month = actual_start.month - 1
        last_year = actual_start.year

    # --- PASO 3: Generar la secuencia de adelantos ---
    advances = []
    curr_m, curr_y = last_month, last_year

    for _ in range(int(qty)):
        curr_m += 1
        if curr_m > 12:
            curr_m, curr_y = 1, curr_y + 1
        
        # Llamamos al motor de cálculo (utils.py)
        breakdown = get_monthly_billing_breakdown(contract_name, curr_m, curr_y)
        
        advances.append({
            "month_num": curr_m,
            "month_name": month_names[curr_m - 1],
            "year": curr_y,
            "rate": breakdown.get("total_to_bill", 0)
        })

    return advances