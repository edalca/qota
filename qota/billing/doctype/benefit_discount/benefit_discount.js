// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Benefit Discount", {
	refresh(frm) {
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
	},
	premises(frm) {
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
	},
});
