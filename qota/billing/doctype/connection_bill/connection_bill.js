// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Connection Bill", {
	setup(frm) {
		frm.set_query("premises", () => {
			return {
				query: "qota.governance.doctype.premises.premises.premises_search",
				filters: { status: "Active", docstatus: 0 },
			};
		});
		frm.set_query("service_contract", () => {
			return {
				query: "qota.governance.doctype.service_contract.service_contract.service_contract_query",
				filters: { status: "Active",docstatus: 1 },
			};
		});
	},
	refresh(frm) {
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
		if (frm.doc.__islocal && !frm.doc.amount) {
			frappe.db.get_single_value("Billing Settings", "default_connection_fee").then((val) => {
				if (val) frm.set_value("amount", val);
			});
		}
	},
	premises(frm) {
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
	},
	service_contract(frm) {
		if (!frm.doc.service_contract) return;

		frappe.db.get_value(
			"Service Contract",
			frm.doc.service_contract,
			["service_category", "subscriber", "full_name", "premises"],
			(r) => {
				if (!r) return;
				frm.set_value("service_category", r.service_category);
				frm.set_value("subscriber", r.subscriber);
				frm.set_value("full_name", r.full_name);
				frm.set_value("premises", r.premises);
				if (r.premises && window.qota && qota.utils && qota.utils.set_premises_description) {
					qota.utils.set_premises_description(frm);
				}
			}
		);
	},

});

