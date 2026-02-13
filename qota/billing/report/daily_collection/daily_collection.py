# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    
    # Añadimos una fila de total al final
    chart = get_chart_data(data)
    report_summary = get_report_summary(data)
    
    return columns, data, None, chart, report_summary

def get_columns():
    return [
        {"label": _("Date"), "fieldname": "payment_date", "fieldtype": "Datetime", "width": 160},
        {"label": _("Receipt"), "fieldname": "name", "fieldtype": "Link", "options": "Payment Receipt", "width": 120},
        {"label": _("Subscriber"), "fieldname": "full_name", "fieldtype": "Data", "width": 180},
        {"label": _("Mode of Payment"), "fieldname": "mode_of_payment", "fieldtype": "Data", "width": 130},
        {"label": _("Reference No."), "fieldname": "reference_no", "fieldtype": "Data", "width": 120},
        {"label": _("Collected Amount"), "fieldname": "total_to_pay", "fieldtype": "Currency", "width": 120},
    ]

def get_data(filters):
    conditions = "docstatus = 1"
    
    if filters.get("from_date"):
        conditions += f" AND DATE(payment_date) >= {frappe.db.escape(filters.get('from_date'))}"
    if filters.get("to_date"):
        conditions += f" AND DATE(payment_date) <= {frappe.db.escape(filters.get('to_date'))}"
    if filters.get("mode_of_payment"):
        conditions += f" AND mode_of_payment = {frappe.db.escape(filters.get('mode_of_payment'))}"

    query = f"""
        SELECT 
            payment_date,
            name,
            full_name,
            mode_of_payment,
            reference_no,
            total_to_pay
        FROM `tabPayment Receipt`
        WHERE {conditions}
        ORDER BY payment_date ASC
    """
    return frappe.db.sql(query, as_dict=1)

def get_chart_data(data):
    """Genera un gráfico de pastel por método de pago"""
    if not data:
        return None

    mode_totals = {}
    for d in data:
        mode = d.get("mode_of_payment")
        mode_totals[mode] = mode_totals.get(mode, 0) + flt(d.get("total_to_pay"))

    return {
        "data": {
            "labels": list(mode_totals.keys()),
            "datasets": [{"values": list(mode_totals.values())}]
        },
        "type": "percentage" # Gráfico de distribución
    }

def get_report_summary(data):
    """Muestra el total recaudado en grande arriba del reporte"""
    if not data:
        return None

    total_collected = sum(flt(d.get("total_to_pay")) for d in data)
    return [
        {
            "value": total_collected,
            "indicator": "Green",
            "label": _("Total Collected"),
            "datatype": "Currency",
        }
    ]