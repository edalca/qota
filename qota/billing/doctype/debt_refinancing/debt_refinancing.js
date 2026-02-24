// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Debt Refinancing", {
	setup: function (frm) {
		// Aplicar el buscador personalizado (Query)
		frm.set_query("service_contract", function () {
			return {
				query: "qota.governance.doctype.service_contract.service_contract.service_contract_query",
				filters: {
					docstatus: 1,
					status: "Active",
				},
			};
		});
	},
	refresh: function (frm) {
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
	},
	service_contract: function (frm) {
		if (frm.doc.service_contract) {
			frappe.call({
				method: "qota.billing.doctype.debt_refinancing.debt_refinancing.get_current_debt",
				args: { contract_id: frm.doc.service_contract },
				callback: function (r) {
					if (r.message !== undefined) {
						frm.set_value("current_total_debt", r.message);
						calculate_visual_plan(frm);
					}
				},
			});
		}
	},

	down_payment: function (frm) {
		calculate_plan(frm);
	},

	installments: function (frm) {
		calculate_plan(frm);
	},
	premises: function (frm) {
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
	},
});

function calculate_plan(frm) {
	if (frm.doc.current_total_debt > 0 && frm.doc.installments > 0) {
		let total = flt(frm.doc.current_total_debt);
		let down = flt(frm.doc.down_payment);

		// Validación básica visual
		if (down >= total) {
			frappe.msgprint(
				__("Down payment cannot cover the full debt. Use Payment Receipt instead."),
			);
			frm.set_value("down_payment", 0);
			return;
		}

		let financed = total - down;
		let monthly = financed / frm.doc.installments;

		frm.set_value("new_financed_debt", financed);
		frm.set_value("monthly_installment_amount", monthly);
	}
}
