// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.query_reports["Advance Payments Report"] = {
    "filters": [
        {
            "fieldname": "service_contract",
            "label": __("Service Contract"),
            "fieldtype": "Link",
            "options": "Service Contract"
        },
        {
            "fieldname": "block",
            "label": __("Block"),
            "fieldtype": "Data"
        },
        {
            "fieldname": "house_number",
            "label": __("House Number"),
            "fieldtype": "Data"
        }
    ]
};