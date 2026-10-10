// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Fine", {
	setup(frm) {
		frm.set_query("service_contract", () => {
			return {
				query: "qota.governance.doctype.service_contract.service_contract.service_contract_query",
				filters: { docstatus: 1 },
			};
		});
	},
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
