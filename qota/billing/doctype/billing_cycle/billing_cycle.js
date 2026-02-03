// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Billing Cycle", {
    refresh: function(frm) {
        // Highlight the Summary Section with a custom color if completed
        if (frm.doc.status === "Completed") {
            frm.set_df_property("summary_section", "label", __("✅ Final Execution Summary"));
        }
        
        // Button to audit the generated entries
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__("Audit Ledger Entries"), () => {
                frappe.set_route("List", "Debt Ledger Entry", {
                    "reference_doctype": frm.doc.doctype,
                    "reference_name": frm.doc.name
                });
            }, __("View"));
        }
    },

    fiscal_month: function(frm) { frm.trigger("auto_calculate_dates"); },
    fiscal_year: function(frm) { frm.trigger("auto_calculate_dates"); },

    auto_calculate_dates: function(frm) {
        if (frm.doc.fiscal_month && frm.doc.fiscal_year) {
            frappe.call({
                doc: frm.doc,
                method: "calculate_service_period",
                callback: function(r) {
                    if (r.message) {
                        frm.set_value("service_start_date", r.message.service_start_date);
                        frm.set_value("service_end_date", r.message.service_end_date);
                        refresh_field("service_start_date");
                        refresh_field("service_end_date");
                    }
                }
            });
        }
    }
});