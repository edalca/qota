// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Meter Reading", {
	onload: function (frm) {
		// 1. Filtro personalizado para buscar solo contratos medidos y activos
		frm.set_query("service_contract", function () {
			return {
				query: "qota.billing.doctype.service_contract.service_contract.contract_search",
				filters: {
					billing_basis: "Metered",
					docstatus: 1,
					status: "Active",
				},
			};
		});
	},

	service_contract: function (frm) {
		// 2. Al seleccionar el contrato, buscamos la lectura anterior
		if (frm.doc.service_contract) {
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Meter Reading",
					filters: { service_contract: frm.doc.service_contract, docstatus: 1 },
					fieldname: "current_reading",
					order_by: "reading_date desc, creation desc",
				},
				callback: function (r) {
					if (r.message && r.message.current_reading) {
						frm.set_value("previous_reading", r.message.current_reading);
					} else {
						// Si no hay lecturas previas, traemos la inicial desde Service Contract
						frappe.db
							.get_value(
								"Service Contract",
								frm.doc.service_contract,
								"start_reading",
							)
							.then((c) => {
								let val = c.message ? c.message.start_reading : 0;
								frm.set_value("previous_reading", val || 0);
							});
					}
				},
			});
		}
	},

	current_reading: function (frm) {
		calculate_consumption(frm);
	},

	previous_reading: function (frm) {
		calculate_consumption(frm);
	},

	premises: function (frm) {
		// 3. Ejecutar utilidad de descripción de predio si existe
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
	},
});

// Función de cálculo con soporte para validación visual
var calculate_consumption = function (frm) {
	if (frm.doc.current_reading != null && frm.doc.previous_reading != null) {
		let consumption = frm.doc.current_reading - frm.doc.previous_reading;
		frm.set_value("consumption", consumption);

		if (consumption < 0) {
			let msg = __("Error! Current reading is lower than previous reading.");
			frm.set_df_property("consumption", "description", `<b style="color:red;">${msg}</b>`);
		} else {
			frm.set_df_property("consumption", "description", "");
		}
	}
};
