# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, date_diff

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("Contract"), "fieldname": "contract", "fieldtype": "Link", "options": "Service Contract", "width": 120},
        {"label": _("Subscriber Name"), "fieldname": "subscriber_name", "fieldtype": "Data", "width": 180},
        {"label": _("Location"), "fieldname": "location", "fieldtype": "Data", "width": 140},
        {"label": _("Total Outstanding"), "fieldname": "total_outstanding", "fieldtype": "Currency", "width": 130},
        {"label": _("Current (1-30)"), "fieldname": "range_1", "fieldtype": "Currency", "width": 110},
        {"label": _("31-60 Days"), "fieldname": "range_2", "fieldtype": "Currency", "width": 110},
        {"label": _("61-90 Days"), "fieldname": "range_3", "fieldtype": "Currency", "width": 110},
        {"label": _("91+ Days"), "fieldname": "range_4", "fieldtype": "Currency", "width": 110},
    ]

def get_data(filters):
    report_date = getdate(filters.get("to_date") or nowdate())
    
    # --- 1. CONSTRUCCIÓN DE LA CONSULTA SQL ---
    conditions = "dle.outstanding_amount > 0 AND dle.docstatus != 2"
    
    if filters.get("premises"):
        conditions += f" AND p.name = {frappe.db.escape(filters.get('premises'))}"

    query = f"""
        SELECT 
            dle.service_contract as contract,
            sc.full_name as subscriber_name,
            p.block, p.house_number,
            dle.outstanding_amount,
            dle.due_date
        FROM `tabDebt Ledger Entry` dle
        INNER JOIN `tabService Contract` sc ON dle.service_contract = sc.name
        LEFT JOIN `tabPremises` p ON sc.premises = p.name
        WHERE {conditions}
        ORDER BY dle.due_date ASC
    """
    
    raw_results = frappe.db.sql(query, as_dict=1)
    
    # --- 2. AGRUPAMIENTO POR CONTRATO ---
    grouped_data = {}

    for d in raw_results:
        contract_id = d.contract
        
        if contract_id not in grouped_data:
            grouped_data[contract_id] = {
                "contract": d.contract,
                "subscriber_name": d.subscriber_name,
                "location": _("Block: {0} House: {1}").format(d.block, d.house_number),
                "total_outstanding": 0,
                "range_1": 0, "range_2": 0, "range_3": 0, "range_4": 0
            }
        
        amount = flt(d.outstanding_amount)
        grouped_data[contract_id]["total_outstanding"] += amount
        
        days = date_diff(report_date, d.due_date) if d.due_date else 0
        
        if days <= 30:
            grouped_data[contract_id]["range_1"] += amount
        elif days <= 60:
            grouped_data[contract_id]["range_2"] += amount
        elif days <= 90:
            grouped_data[contract_id]["range_3"] += amount
        else:
            grouped_data[contract_id]["range_4"] += amount
            
    return list(grouped_data.values())