// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

 frappe.ui.form.on("Service Contract Log", {
     refresh: function(frm) {
        // Set visual indicators on the top header
        frm.set_read_only();
        frm.disable_save();
        frm.page.clear_secondary_action();
 
    }
 });
