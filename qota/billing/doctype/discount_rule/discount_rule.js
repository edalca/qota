// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Discount Rule", {
	refresh: function (frm) {
		if (frm.doc.condition_type === "Age") {
			frm.set_df_property("minimum_age", "reqd", 1);
		}
	},
	condition_type: function (frm) {
		// Limpiar campos si cambia el tipo
		if (frm.doc.condition_type !== "Age") {
			frm.set_value("minimum_age", 0);
			frm.set_value("maximum_age", 0);
		}
	},
});
