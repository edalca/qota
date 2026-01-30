// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Tariff", {
	refresh: function (frm) {
		if (!frm.is_new() && frm.doc.status === "Active") {
			frm.set_df_property(
				"status",
				"description",
				'<b style="color:green;">' +
					__("This tariff is currently used for billing.") +
					"</b>",
			);
		}
	},

	min_consumption: function (frm) {
		// Si cambia el mínimo, la primera fila de la tabla debe iniciar ahí
		if (frm.doc.ranges && frm.doc.ranges.length > 0) {
			frappe.model.set_value(
				frm.doc.ranges[0].doctype,
				frm.doc.ranges[0].name,
				"from_unit",
				frm.doc.min_consumption,
			);
		}
	},
});

frappe.ui.form.on("Service Tariff Range", {
	ranges_add: function (frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);

		if (frm.doc.ranges && frm.doc.ranges.length > 1) {
			let last_row = frm.doc.ranges[row.idx - 2];
			if (last_row && last_row.to_unit) {
				frappe.model.set_value(cdt, cdn, "from_unit", last_row.to_unit);
			}
		} else {
			frappe.model.set_value(cdt, cdn, "from_unit", frm.doc.min_consumption || 0);
		}
	},

	to_unit: function (frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		// Si el usuario cambia el 'hasta', actualizamos el 'desde' de la siguiente fila
		if (frm.doc.ranges.length > row.idx) {
			let next_row = frm.doc.ranges[row.idx];
			frappe.model.set_value(next_row.doctype, next_row.name, "from_unit", row.to_unit);
		}
	},
});
