// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Debt Ledger Entry", {
    setup: function(frm) {
        // Filter: Only allow linking to Open Billing Years
        frm.set_query("fiscal_year", () => {
            return {
                filters: { is_closed: 0 }
            };
        });
    },

    refresh: function(frm) {
        // Set visual indicators on the top header
        frm.set_read_only();
        frm.disable_save();
        
        if (frm.doc.status === "Paid") {
            frm.page.set_indicator(__("Paid"), "green");
        } else if (frm.doc.status === "Partially Paid") {
            frm.page.set_indicator(__("Partially Paid"), "orange");
        } else {
            frm.page.set_indicator(__("Unpaid"), "red");
        }

        // Add an Audit button to see exactly which receipts paid this debt
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__("View Allocations"), () => {
                frappe.set_route("List", "Payment Allocation", {
                    "debt_ledger_entry": frm.doc.name
                });
            }, __("Audit"));
        }
    }
});