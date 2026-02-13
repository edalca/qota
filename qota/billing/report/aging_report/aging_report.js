// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.query_reports["Aging Report"] = {
    "filters": [
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.nowdate(),
            "reqd": 1
        },
        {
            "fieldname": "premises",
            "label": __("Specific Premises"),
            "fieldtype": "Link",
            "options": "Premises"
        }
    ]
};