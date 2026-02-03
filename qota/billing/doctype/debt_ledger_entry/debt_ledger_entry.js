// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Debt Ledger Entry", {
	refresh(frm) {
		// Ocultar botón de guardar si el documento está enviado
		if (!frm.is_new()) {
			frm.disable_save();
			frm.set_read_only();
		}
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
	},
	premises: function (frm) {
		// 3. Ejecutar utilidad de descripción de predio si existe
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
	},
});
