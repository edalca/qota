// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Billing Settings", {
	refresh: function (frm) {
		// Añadir una descripción dinámica para explicar el ciclo
		if (frm.doc.cycle_start_day) {
			let next_day = frm.doc.cycle_start_day - 1;
			if (next_day === 0) next_day = 28;

			frm.set_df_property(
				"cycle_start_day",
				"description",
				__("Current billing will run from day {0} to day {1} of the following month.", [
					frm.doc.cycle_start_day,
					next_day,
				]),
			);
		}
	},

	cycle_start_day: function (frm) {
		if (frm.doc.cycle_start_day > 28) {
			frappe.msgprint(
				__(
					"Note: It is recommended to use a day between 1 and 28 to avoid issues with shorter months like February.",
				),
			);
		}
	},
});
