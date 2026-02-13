# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    """Definición de columnas en inglés para traducciones"""
    return [
        {"label": _("Receipt"), "fieldname": "parent", "fieldtype": "Link", "options": "Payment Receipt", "width": 120},
        {"label": _("Contract"), "fieldname": "service_contract", "fieldtype": "Link", "options": "Service Contract", "width": 120},
        {"label": _("Subscriber"), "fieldname": "subscriber_name", "fieldtype": "Data", "width": 180},
        {"label": _("Payment Concept"), "fieldname": "payment_concept", "fieldtype": "Data", "width": 130},
        {"label": _("Period"), "fieldname": "billing_period", "fieldtype": "Data", "width": 100},
        {"label": _("Original Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Available Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 120},
    ]

def get_data(filters):
    """Obtiene los ítems de recibos con saldo disponible"""
    conditions = "item.balance > 0 AND parent.docstatus = 1"
    
    if filters.get("service_contract"):
        conditions += f" AND parent.service_contract = {frappe.db.escape(filters.get('service_contract'))}"

    query = f"""
        SELECT 
            item.parent,
            parent.service_contract,
            sc.full_name as subscriber_name,
            item.payment_concept,
            item.billing_period,
            item.amount,
            item.balance
        FROM `tabPayment Receipt Item` item
        INNER JOIN `tabPayment Receipt` parent ON item.parent = parent.name
        INNER JOIN `tabService Contract` sc ON parent.service_contract = sc.name
        WHERE {conditions}
        ORDER BY parent.payment_date ASC
    """
    
    return frappe.db.sql(query, as_dict=1)