// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Bill", {
	refresh(frm) {},
	contract(frm) {
		qota.utils.set_premises_description(frm);
	},
});
