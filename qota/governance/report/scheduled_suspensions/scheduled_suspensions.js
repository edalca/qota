// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.query_reports["Scheduled Suspensions"] = {
    filters: [
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: "Scheduled\nDraft",
            default: "Scheduled",
        },
        {
            fieldname: "reason",
            label: __("Reason"),
            fieldtype: "Select",
            options: "\nArrears\nSubscriber Request\nFraud / Bypass\nSanction\nMaintenance\nOther",
        },
        {
            fieldname: "premises",
            label: __("Premises"),
            fieldtype: "Link",
            options: "Premises",
        },
    ],

    onload: function (report) {
        report.page.add_inner_button(__("Print Selected"), function () {
            const checked = report.datatable.rowmanager.getCheckedRows();
            if (!checked.length) {
                frappe.msgprint(__("Select at least one suspension to print."));
                return;
            }
            const names = checked.map(i => report.data[i].suspension);
            const url = frappe.utils.get_url_to_form("Service Suspension", names[0]);
            names.forEach(name => {
                const print_url = `/printview?doctype=Service+Suspension&name=${encodeURIComponent(name)}&format=Service+Suspension+Notice&no_letterhead=0&_lang=es`;
                window.open(print_url, "_blank");
            });
        });
    },
};
