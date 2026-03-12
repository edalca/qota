// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Expense Voucher", {
    onload(frm) {
        // Filter only active categories for better UX
        frm.set_query("expense_category", function() {
            return {
                filters: { is_active: 1 }
            };
        });
    },

    refresh(frm) {
        // Maintain UI consistency for submitted documents
        if (frm.doc.docstatus === 1) {
            frm.set_df_property("amount", "read_only", 1);
            frm.set_df_property("expense_category", "read_only", 1);
            frm.set_df_property("payee", "read_only", 1);
        }
    }
});