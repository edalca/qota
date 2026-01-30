// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Premises", {
	refresh: function (frm) {
		// Estética: Bloqueo visual de campos permanentes si no es nuevo
		if (!frm.is_new()) {
			["registration_id", "sector", "block", "house_number"].forEach((f) => {
				frm.set_df_property(f, "read_only", 1);
			});
		}
	},
});
