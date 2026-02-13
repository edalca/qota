# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate

def execute(filters=None):
    if not filters.get("service_contract"):
        return [], []

    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": _("Doctype"), "fieldname": "reference_doctype", "fieldtype": "Data", "width": 150},
        {"label": _("Reference"), "fieldname": "reference", "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 140},
        {"label": _("Billing Period"), "fieldname": "billing_period", "fieldtype": "Data", "width": 120},
        {"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 250},
        {"label": _("Debit (Charges)"), "fieldname": "debit", "fieldtype": "Currency", "width": 120},
        {"label": _("Credit (Payments)"), "fieldname": "credit", "fieldtype": "Currency", "width": 120},
        {"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 120},
    ]

def get_data(filters):
    contract = filters.get("service_contract")
    
    # 1. Obtenemos CARGOS (Monthly Bills / Debt Ledger)
    # Buscamos la creación de la deuda
    query = f"""
        (SELECT 
            creation as posting_date,
            name as reference,
            'Debt Ledger Entry' as reference_doctype,
            description,
            billing_period,
            amount as debit,
            0 as credit
        FROM `tabDebt Ledger Entry`
        WHERE service_contract = %(contract)s AND docstatus != 2)
        
        UNION ALL
        
        (SELECT 
            parent.payment_date as posting_date,
            parent.name as reference,            -- Cambiado: Ahora es el ID del Recibo (RCP-...)
            'Payment Receipt' as reference_doctype, -- Cambiado: El Doctype para el link
            item.description,
            item.billing_period,
            0 as debit,
            item.amount as credit
        FROM `tabPayment Receipt Item` item
        INNER JOIN `tabPayment Receipt` parent ON item.parent = parent.name
        WHERE parent.service_contract = %(contract)s AND parent.docstatus = 1)
        
        ORDER BY posting_date ASC
    """
    
    raw_entries = frappe.db.sql(query, {"contract": contract}, as_dict=1)
    
    # 2. CÁLCULO DEL SALDO ACUMULADO (Running Balance)
    data = []
    running_balance = 0
    
    for entry in raw_entries:
        running_balance += flt(entry.debit) - flt(entry.credit)  
        entry["balance"] = running_balance
        data.append(entry)
        
    return data