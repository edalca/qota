// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.query_reports["Delinquent Subscribers"] = {
    onload: function (report) {
        frappe.db.get_single_value("Billing Settings", "suspension_months_limit").then((val) => {
            if (val) {
                report.set_filter_value("min_periods", val);
            }
        });
    },
    filters: [
        {
            fieldname: "contract_status",
            label: __("Contract Status"),
            fieldtype: "Select",
            options: "\nActive\nSuspended",
            default: "Active",
        },
        {
            fieldname: "min_periods",
            label: __("Minimum Overdue Periods"),
            fieldtype: "Int",
            default: 1,
        },
        {
            fieldname: "premises",
            label: __("Premises"),
            fieldtype: "Link",
            options: "Premises",
        },
    ],
};
