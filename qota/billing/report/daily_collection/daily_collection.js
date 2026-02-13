// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.query_reports["Daily Collection"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.nowdate()
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.nowdate()
        },
        {
            "fieldname": "mode_of_payment",
            "label": __("Mode of Payment"),
            "fieldtype": "Select",
            "options": "\nCash\nBank Transfer\nCheck\nCredit Card"
        }
    ]
};