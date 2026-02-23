// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Discount Rule", {
    refresh: function(frm) {
        // Initial UI setup
        frm.trigger("toggle_fields");
    },

    condition_type: function(frm) {
        // Clear age fields if condition is not Age
        if (frm.doc.condition_type !== "Age") {
            frm.set_value("minimum_age", 0);
            frm.set_value("maximum_age", 0);
        }
        frm.trigger("toggle_fields");
    },

    discount_type: function(frm) {
        // Clear opposite field when type changes
        if (frm.doc.discount_type === "Fixed Amount") {
            frm.set_value("discount_percentage", 0);
        } else {
            frm.set_value("fixed_amount", 0);
        }
        frm.trigger("toggle_fields");
    },

    toggle_fields: function(frm) {
        /**
         * Dynamically sets fields as mandatory (reqd) based on selection.
         * This improves data integrity before the Python validation kicks in.
         */
        
        // 1. Logic for Eligibility Conditions
        const is_age = frm.doc.condition_type === "Age";
        frm.set_df_property("minimum_age", "reqd", is_age ? 1 : 0);
        
        // 2. Logic for Discount Calculation
        const is_fixed = frm.doc.discount_type === "Fixed Amount";
        frm.set_df_property("fixed_amount", "reqd", is_fixed ? 1 : 0);
        frm.set_df_property("discount_percentage", "reqd", is_fixed ? 0 : 1);
        
        frm.refresh_fields();
    }
});