# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today, getdate, add_months, format_date,nowdate,add_days
from datetime import date
import json

class PaymentReceipt(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from qota.billing.doctype.payment_receipt_item.payment_receipt_item import PaymentReceiptItem

        amended_from: DF.Link | None
        current_debt: DF.Currency
        full_name: DF.Data | None
        mode_of_payment: DF.Literal["Cash", "Bank Transfer", "Check", "Credit Card"]
        payment_date: DF.Datetime
        payment_items: DF.Table[PaymentReceiptItem]
        premises: DF.Link | None
        reference_no: DF.Data | None
        remarks: DF.SmallText | None
        service_contract: DF.Link
        status: DF.Literal["Draft", "Paid", "Cancelled"]
        subscriber: DF.Link | None
        total_pending: DF.Currency
        total_to_pay: DF.Currency
        unallocated_amount: DF.Currency
    # end: auto-generated types

    def validate(self):
        """
        Este método se ejecuta SIEMPRE al guardar. 
        Asegura que los totales sean correctos independientemente del JavaScript.
        """
        self.calculate_totals()
        self.status_update()


    def on_submit(self):
        """
        Al confirmar el recibo, actualizamos el saldo de las deudas vinculadas.
        """
        self.process_ledger_updates(cancel=False)

    def on_cancel(self):
        """
        Al cancelar el recibo, devolvemos el saldo a las deudas (revertir operación).
        """
        self.process_ledger_updates(cancel=True)

    def status_update(self):
        if self.docstatus == 0:
            self.status = "Draft"
        elif self.docstatus == 1:
            self.status = "Paid"
        elif self.docstatus == 2:
            self.status = "Cancelled"


    def process_ledger_updates(self, cancel=False):
        for item in self.payment_items:
            # Solo procesamos si el ítem está vinculado a una deuda existente
            if item.debt_ledger_entry:
                debt = frappe.get_doc("Debt Ledger Entry", item.debt_ledger_entry)
  
                if cancel:
                    # CASO CANCELAR: Devolvemos el dinero a la deuda (Sumar)
                    debt.outstanding_amount += flt(item.amount)

                    debt.paid_amount -= flt(item.amount)
                        
                else:
                    # CASO SUBMIT: Restamos el dinero a la deuda
                    # Validación de seguridad
                    if flt(item.amount) > flt(debt.outstanding_amount):
                        frappe.throw(
                            _("Payment amount ({0}) exceeds the outstanding balance ({1}) for debt {2}.").format(
                                item.amount, debt.outstanding_amount, item.debt_ledger_entry
                            )
                        )
                    
                    debt.outstanding_amount -= flt(item.amount)
                    debt.paid_amount += flt(item.amount)


                if flt(debt.outstanding_amount) <= 0:
                    debt.status = "Paid"
                # Si ha pagado algo pero sigue debiendo -> Partially Paid
                elif flt(debt.paid_amount) > 0:
                    debt.status = "Partially Paid"
                # Si no ha pagado nada -> Unpaid
                else:
                    debt.status = "Unpaid"

                # Guardar cambios ignorando permisos (porque el Ledger suele ser Read Only)
                debt.flags.ignore_validate_update_after_submit = True
                debt.save(ignore_permissions=True)

                # Guardamos los cambios en el Debt Ledger Entry sin validar permisos de nuevo
                debt.flags.ignore_validate_update_after_submit = True
                debt.save(ignore_permissions=True)

    def calculate_totals(self):
        total_to_pay = 0.0
        unallocated_amount = 0.0

        # Recorremos la única tabla: payment_items
        if self.get("payment_items"):
            for item in self.payment_items:
                # Sumar al total pagado
                total_to_pay += flt(item.amount)

                # Si NO tiene debt_ledger_entry, es un adelanto (unallocated)
                if not item.debt_ledger_entry:
                    unallocated_amount += flt(item.amount)

        self.total_to_pay = total_to_pay
        self.unallocated_amount = unallocated_amount
        
        self.total_pending = flt(self.current_debt) - total_to_pay + unallocated_amount



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
        fields=["name as debt_id", "entry_type as payment_concept", "outstanding_amount as amount", "due_date", "description","billing_period"],
        order_by="creation asc"
    )

    current_date = getdate(today())
    for d in debts:
        # Una deuda es obligatoria si ya pasó su fecha de vencimiento
        d['days_diff'] = frappe.utils.date_diff(d['due_date'], current_date) if d['due_date'] else 0
        
    return {
        "debts": debts,
        "current_debt": sum(flt(d['amount']) for d in debts)
    }

@frappe.whitelist()
def get_next_billing_advances(contract_name, qty=12):
    """
    Calcula los próximos meses a pagar por adelantado.
    Calcula dinámicamente start_date y end_date para cada mes futuro 
    y los envía al motor de breakdown.
    """
    from qota.billing.utils import get_monthly_billing_breakdown

    contract = frappe.get_doc("Service Contract", contract_name)
    
    # 1. Obtener configuración global de fechas
    settings = frappe.get_single("Billing Settings")
    start_day = int(settings.cycle_start_day or 1)
    
    # Mapeo de nombres de meses
    month_names = [
        "January", "February", "March", "April", "May", "June", 
        "July", "August", "September", "October", "November", "December"
    ]

    # ------------------------------------------------------------------
    # PASO 1 Y 2: DETERMINAR PUNTO DE PARTIDA (Historial de Deuda y Adelantos)
    # ------------------------------------------------------------------
    # (Mantenemos la lógica de búsqueda de last_debt_date y last_advance_date)
    last_debt_date = None
    last_entry = frappe.get_all("Debt Ledger Entry",
        filters={"service_contract": contract_name, "entry_type": "Monthly Fee", "docstatus": ["!=", 2]},
        fields=["reference_name"], order_by="creation desc", limit=1
    )
    if last_entry and last_entry[0].reference_name:
        cycle_data = frappe.db.get_value("Billing Cycle", last_entry[0].reference_name, ["fiscal_month", "fiscal_year"], as_dict=True)
        if cycle_data:
            year_val = frappe.db.get_value("Billing Year", cycle_data.fiscal_year, "year_name")
            last_debt_date = date(int(year_val), month_names.index(cycle_data.fiscal_month) + 1, 1)

    last_advance_date = None
    paid_periods = frappe.db.sql("""
        SELECT billing_period FROM `tabPayment Receipt Item`
        WHERE parent IN (SELECT name FROM `tabPayment Receipt` WHERE service_contract = %s AND docstatus = 1)
        AND billing_period IS NOT NULL AND payment_concept = 'Monthly Fee'
    """, (contract_name), as_dict=True)
    
    found_dates = []
    for row in paid_periods:
        parts = row.billing_period.split('-')
        found_dates.append(date(int(parts[1]), int(parts[0]), 1))
    if found_dates: last_advance_date = max(found_dates)

    start_point = last_debt_date
    if last_advance_date and (not last_debt_date or last_advance_date > last_debt_date):
        start_point = last_advance_date

    # ------------------------------------------------------------------
    # PASO 3: MAPEO DE AÑOS Y VALIDACIÓN INICIAL
    # ------------------------------------------------------------------
    open_years_map = { 
        int(y.year_name): y.name 
        for y in frappe.get_all("Billing Year", filters={"is_closed": 0}, fields=["name", "year_name"]) 
    }
    
    if not start_point:
        contract_start = getdate(contract.start_date)
        min_y = min(open_years_map.keys())
        start_point = contract_start if contract_start.year >= min_y else date(min_y, 1, 1)
        current_date = add_months(start_point, -1)
    else:
        current_date = start_point

    # ------------------------------------------------------------------
    # PASO 4: GENERAR ADELANTOS CON FECHAS CALCULADAS
    # ------------------------------------------------------------------
    advances = []
    today_date = nowdate()

    for i in range(int(qty)):
        next_month_date = add_months(current_date, 1)
        y_num = next_month_date.year
        m_num = next_month_date.month

        # A. Verificar si el año está abierto
        fiscal_year_link = open_years_map.get(y_num)
        if not fiscal_year_link: break

        fiscal_month_str = month_names[m_num - 1]

        # B. CALCULAR START_DATE Y END_DATE PARA EL PERIODO FUTURO
        # Basado en la lógica del Billing Cycle
        if start_day == 1:
            period_start = date(y_num, m_num, 1)
            # El último día del mes es el día 0 del mes siguiente
            period_end = add_days(add_months(period_start, 1), -1)
        else:
            period_start = date(y_num, m_num, start_day)
            period_end = add_days(add_months(period_start, 1), -1)

        # C. LLAMADA AL MOTOR CON LOS 5 PARÁMETROS
        breakdown = get_monthly_billing_breakdown(
            contract_name = contract_name,
            billing_month = fiscal_month_str, # "January"
            billing_year  = fiscal_year_link,  # "BY-2026"
            start_date    = period_start,     # Date object
            end_date      = period_end        # Date object
        )
        
        # D. Empaquetar resultados
        advances.append({
            "billing_period": next_month_date.strftime("%m-%Y"),
            "month_num": m_num,
            "year": y_num,
            "due_date": today_date,
            "amount": flt(breakdown.get("total_to_bill", 0)),
            "description": _("Monthly Fee: {0}").format(format_date(next_month_date, 'MMMM YYYY')),
            "billing_details": json.dumps(breakdown.get("detailed_items", []))
        })
        
        current_date = next_month_date

    return advances