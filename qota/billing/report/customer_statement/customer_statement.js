// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.query_reports["Customer Statement"] = {
    "filters": [
        {
            "fieldname": "service_contract",
            "label": __("Service Contract"),
            "fieldtype": "Link",
            "options": "Service Contract",
            "reqd": 1 // Obligatorio
        },
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date"
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.nowdate()
        }
    ]
};