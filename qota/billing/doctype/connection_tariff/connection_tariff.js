// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Connection Tariff", {
	total_fee: function (frm) {
		// Sugerir que la prima sea al menos el 50% por defecto si está vacío
		if (frm.doc.total_fee > 0 && !frm.doc.min_down_payment) {
			frm.set_value("min_down_payment", frm.doc.total_fee * 0.5);
		}
	},
});
