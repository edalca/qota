# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today
from qota.billing.doctype.debt_ledger_entry.debt_ledger_entry import DebtLedgerEntry


class PaymentReceipt(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from qota.billing.doctype.payment_receipt_item.payment_receipt_item import PaymentReceiptItem

        amended_from: DF.Link | None
        amount_paid: DF.Currency
        current_debt: DF.Currency
        is_reconnection_payment: DF.Check
        mode_of_payment: DF.Literal["Cash", "Bank Transfer", "Check", "Credit Card"]
        monthly_rate_estimation: DF.Currency
        payment_date: DF.Date
        payment_items: DF.Table[PaymentReceiptItem]
        premises: DF.Link | None
        reconnection_charge: DF.Currency
        reference_no: DF.Data | None
        remarks: DF.SmallText | None
        resulting_balance: DF.Data | None
        service_contract: DF.Link
        subscriber: DF.Data | None
        total_to_pay: DF.Currency
    # end: auto-generated types

    def validate(self):
        if self.amount_paid <= 0:
            frappe.throw(_("Amount paid must be greater than zero."))
        
        # 1. Validar que la suma de la tabla coincida con el total pagado (si hay items)
        self.validate_totals()

        # 2. Validaciones de Reconexión (Tu código original)
        if self.is_reconnection_payment and self.reconnection_charge > 0:
            # Verificamos si el pago total cubre al menos la reconexión
            if self.amount_paid < self.reconnection_charge:
                frappe.msgprint(_("Warning: Payment is less than the Reconnection Charge. Service might not be restored automatically."))

    def validate_totals(self):
        """Si hay items en la tabla, el total debe coincidir"""
        if self.payment_items:
            items_total = sum(flt(item.amount) for item in self.payment_items)
            
            # Si hay cargo de reconexión, se suma aparte porque no suele estar en la tabla de meses
            if self.is_reconnection_payment:
                items_total += flt(self.reconnection_charge)
            
            # Permitimos una pequeña diferencia por redondeo, pero actualizamos el header si difiere
            if abs(flt(self.amount_paid) - items_total) > 0.01:
                # Opcional: Forzar el valor o lanzar error. 
                # Aquí actualizamos el valor para ayudar al cajero.
                self.amount_paid = items_total

    def on_submit(self):
        # --- A. LÓGICA DE RECONEXIÓN (Tu código original) ---
        if self.is_reconnection_payment and self.reconnection_charge > 0:
            # 1. Crear la Deuda del Cargo (Adjustment)
            DebtLedgerEntry.create_entry(
                contract=self.service_contract,
                entry_type="Reconnection Fee", 
                amount=self.reconnection_charge, 
                ref_dt="Payment Receipt",
                ref_dn=self.name,
                posting_date=self.payment_date,
                description=_("Automatic Reconnection Charge")
            )
            
            # 2. Crear el PAGO específico de ese cargo
            DebtLedgerEntry.create_entry(
                contract=self.service_contract,
                entry_type="Payment",
                amount= -1 * self.reconnection_charge,
                ref_dt="Payment Receipt",
                ref_dn=self.name,
                posting_date=self.payment_date,
                description=_("Payment for Reconnection Fee")
            )
            
            # 3. Reactivar Contrato
            frappe.db.set_value("Service Contract", self.service_contract, {
                "status": "Active",
                "last_status_change": self.payment_date
            })
            frappe.msgprint(_("Service Contract reactivated successfully."), indicator='green')

        # --- B. LÓGICA DE PAGO MENSUAL (Nueva Lógica Detallada) ---
        
        if self.payment_items:
            # Si el cajero seleccionó meses específicos, creamos una entrada por cada mes
            for item in self.payment_items:
                DebtLedgerEntry.create_entry(
                    contract=self.service_contract,
                    entry_type="Payment",
                    amount= -1 * flt(item.amount), 
                    ref_dt="Payment Receipt",
                    ref_dn=self.name,
                    posting_date=self.payment_date,
                    # GUARDAMOS LA REFERENCIA DEL MES Y AÑO
                    fiscal_year=item.year,
                    fiscal_month=item.month,
                    description=f"Payment for {item.month} {item.year}"
                )
        else:
            # FALLBACK: Si no usaron la tabla (pago global), usamos la lógica antigua
            # Restamos la reconexión si ya se pagó arriba para no duplicar
            remaining_amount = self.amount_paid
            if self.is_reconnection_payment:
                remaining_amount -= self.reconnection_charge
            
            if remaining_amount > 0:
                DebtLedgerEntry.create_entry(
                    contract=self.service_contract,
                    entry_type="Payment",
                    amount= -1 * remaining_amount, 
                    ref_dt="Payment Receipt",
                    ref_dn=self.name,
                    posting_date=self.payment_date,
                    description="Lump Sum Payment"
                )
        
        frappe.msgprint(_("Payment of {0} registered successfully.").format(self.amount_paid), indicator='green')

    def on_cancel(self):
        pass
        # Reversión inteligente
        #if self.payment_items:
        #    for item in self.payment_items:
        #        DebtLedgerEntry.create_entry(
        #            contract=self.service_contract,
        #            entry_type="Payment Reversal",
        #            amount= flt(item.amount),
        #            ref_dt="Payment Receipt",
        #            ref_dn=self.name,
        #            posting_date=today(),
        #            fiscal_year=item.year,
        #            fiscal_month=item.month,
        #            description=f"Cancelled Payment {item.month} {item.year}"
        #        )
        #else:
            # Reversión global antigua
        #    reversal_amount = self.amount_paid
        #    if self.is_reconnection_payment:
        #        reversal_amount -= self.reconnection_charge # Ajustar si es necesario reversar reconexión aparte
                
        #    DebtLedgerEntry.create_entry(
        #        contract=self.service_contract,
        #        entry_type="Payment Reversal",
        #        amount= reversal_amount, 
        #        ref_dt="Payment Receipt",
        #        ref_dn=self.name,
        #        posting_date=today()
        #    )

        #if self.is_reconnection_payment:
        #    frappe.msgprint(_("Note: This payment was for a reconnection. Check if the Service Contract needs to be suspended again manually."), indicator='orange')

# --- API METHODS (Para que funcionen los botones del JS) ---

@frappe.whitelist()
def get_payment_info(contract):
    """ 
    Devuelve Deuda Total Ledger, Estimado Mensual y Datos de Reconexión
    """
    # 1. Deuda Ledger
    balance = frappe.db.sql("""
        SELECT SUM(amount) FROM `tabDebt Ledger Entry` 
        WHERE service_contract = %s
    """, (contract,))
    current_debt = flt(balance[0][0]) if balance else 0.0

    # 2. Datos del Contrato
    contract_doc = frappe.db.get_value("Service Contract", contract, 
        ["status", "service_category"], as_dict=True)

    # 3. Estimado Mensual
    monthly_est = 0.0
    try:
        from qota.billing.doctype.service_rate.service_rate import get_estimated_monthly_cost
        monthly_est = get_estimated_monthly_cost(contract)
    except Exception as e:
        monthly_est = 0.0

    # 4. Lógica de Reconexión
    reconnection_charge = 0.0
    is_reconnection = 0
    
    if contract_doc and contract_doc.status == "Suspended":
        is_reconnection = 1
        try:
            fee_amount = frappe.db.get_value("Reconnection Fee", 
                {"service_category": contract_doc.service_category, "active": 1}, 
                "amount"
            )
            reconnection_charge = flt(fee_amount) if fee_amount else 0.0
        except Exception:
            reconnection_charge = 0.0

    return {
        "current_debt": current_debt,
        "monthly_est": monthly_est,
        "is_reconnection": is_reconnection,
        "reconnection_charge": reconnection_charge
    }

@frappe.whitelist()
def get_pending_debts(contract):
    """
    Busca TODA deuda pendiente en el Ledger (Mensualidades, Conexiones, Multas, etc.)
    Agrupa por Tipo, Año y Mes.
    """
    
    # 1. Consulta SQL: Agrupamos por Tipo de Entrada también
    pending_ledger = frappe.db.sql("""
        SELECT 
            entry_type,
            fiscal_month, 
            fiscal_year, 
            SUM(amount) as pending_balance
        FROM `tabDebt Ledger Entry`
        WHERE service_contract = %s
          AND docstatus = 1
        GROUP BY entry_type, fiscal_year, fiscal_month
        HAVING pending_balance > 0.01
    """, (contract,), as_dict=True)

    if not pending_ledger:
        return []

    # 2. Mapeo de Orden para mostrar primero Cargos Varios y luego Meses Viejos
    months_map = {
        "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
        "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12
    }

    # Ordenar: Primero por Año, luego Mes. 
    # (Los cargos sin mes/año quedarán arriba o abajo según Python sort, 
    # generalmente None es menor que números, así que saldrán primero).
    pending_ledger.sort(key=lambda x: (x.fiscal_year or 0, months_map.get(x.fiscal_month, 0)))

    result_list = []
    
    for row in pending_ledger:
        # Definir Concepto y Descripción según el Ledger
        concept = "Monthly Fee"
        description = ""
        
        if row.entry_type == "Monthly Bill":
            concept = "Monthly Fee"
        elif row.entry_type == "Connection Fee":
            concept = "Other" # O "Connection Fee" si agregas esa opción al Select del Item
            description = "Pending Connection Fee"
        elif row.entry_type == "Late Fee":
            concept = "Other"
            description = "Late Payment Penalty"
        elif row.entry_type == "Adjustment":
            concept = "Other"
            description = "Adjustment / Reconnection"
        else:
            concept = "Other"
            description = f"{row.entry_type} Balance"

        # Construir fila
        result_list.append({
            "payment_concept": concept,
            "month": row.fiscal_month, # Puede venir vacío si es Connection Fee
            "year": row.fiscal_year,
            "amount": row.pending_balance,
            "description": description
        })

    return result_list

@frappe.whitelist()
def get_account_status(contract, year):
    """
    Botón 'View Account Status': Genera el reporte visual del Dialog.
    Compara lo facturado (Ledger) vs lo pagado (Ledger) mes a mes.
    """
    months = ["January", "February", "March", "April", "May", "June", 
              "July", "August", "September", "October", "November", "December"]
    
    status_report = []

    # Obtener movimientos del Ledger para ese año
    ledger_entries = frappe.db.sql("""
        SELECT entry_type, fiscal_month, amount 
        FROM `tabDebt Ledger Entry`
        WHERE service_contract = %s AND fiscal_year = %s AND docstatus = 1
    """, (contract, year), as_dict=True)

    for m in months:
        # Filtrar entradas de este mes
        entries = [e for e in ledger_entries if e.fiscal_month == m]
        
        # Monthly Bill: Genera deuda positiva
        bill_amount = sum(flt(e.amount) for e in entries if e.entry_type == "Monthly Bill")
        
        # Payment: Son valores negativos, los pasamos a absoluto para comparar
        paid_amount = sum(abs(flt(e.amount)) for e in entries if e.entry_type == "Payment")
        
        status = "No Generated"
        color = "gray"
        
        if bill_amount > 0:
            if paid_amount >= bill_amount:
                status = "Paid"
                color = "green"
            else:
                status = "Due"
                color = "red"
        elif paid_amount > 0:
            status = "Paid (Advance)"
            color = "blue"
            
        status_report.append({
            "month": m,
            "bill": bill_amount,
            "paid": paid_amount,
            "status": status,
            "color": color
        })

    return status_report

@frappe.whitelist()
def get_next_payable_month(contract):
    """
    Busca cuál fue el último mes pagado en el historial y devuelve 
    la fecha de inicio para el SIGUIENTE mes a pagar.
    """
    import datetime
    
    # Buscamos el último pago de Mensualidad registrado
    last_payment = frappe.db.sql("""
        SELECT item.year, item.month
        FROM `tabPayment Receipt Item` item
        JOIN `tabPayment Receipt` head ON item.parent = head.name
        WHERE head.service_contract = %s
          AND head.docstatus = 1
          AND item.payment_concept = 'Monthly Fee'
        ORDER BY item.year DESC, 
                 FIELD(item.month, 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December') DESC
        LIMIT 1
    """, (contract,), as_dict=True)

    today = datetime.date.today()
    
    if not last_payment:
        # Si nunca ha pagado nada, empezamos desde el mes actual
        return {"year": today.year, "month_idx": today.month - 1} # Python month es 1-12, JS usa 0-11

    # Mapear nombre de mes a número
    months_map = {
        "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
        "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12
    }
    
    last_year = last_payment[0].year
    last_month_name = last_payment[0].month
    last_month_num = months_map.get(last_month_name, 1)

    # Calcular el siguiente mes
    next_month_num = last_month_num + 1
    next_year = last_year
    
    if next_month_num > 12:
        next_month_num = 1
        next_year += 1
        
    return {"year": next_year, "month_idx": next_month_num - 1} # Restamos 1 para índice JS (0-11)