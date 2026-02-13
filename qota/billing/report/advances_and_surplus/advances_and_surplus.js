// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.query_reports["Advances and Surplus"] = {
    "filters": [
        {
            "fieldname": "service_contract",
            "label": __("Service Contract"),
            "fieldtype": "Link",
            "options": "Service Contract"
        }
    ]
};