// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Contract", {
	setup: function (frm) {
		// Filter: only active subscribers and premises
		frm.set_query("subscriber", () => {
			return { filters: { status: "Active" } };
		});
		frm.set_query("premises", () => {
			return {
				query: "qota.governance.doctype.premises.premises.premises_search",
				filters: { status: "Active", docstatus: 0 },
			};
		});
	},

	refresh: function (frm) {
		const fields_to_lock = [
			"status",
			"billing_basis",
			"meter_id",
			"start_reading",
			"has_cistern",
			"cistern_capacity",
		];
		if (frm.doc.docstatus !== 0) {
			fields_to_lock.forEach((field) => {
				frm.set_df_property(field, "read_only", 1);
			});
		}
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
		// 1. Buttons for new records
		if (frm.is_new()) {
			frm.add_custom_button(
				__("Quick Add Subscriber"),
				() => frappe.new_doc("Subscriber"),
				__("Actions"),
			);
			frm.add_custom_button(
				__("Quick Add Premises"),
				() => frappe.new_doc("Premises"),
				__("Actions"),
			);
		}

		// 2. Actions for Active/Suspended contracts
		const terminal_statuses = ["Closed", "Cancelled"];

		if (frm.doc.docstatus === 1 && !terminal_statuses.includes(frm.doc.status)) {
			// ACTION: Cistern Management
			let cistern_label = frm.doc.has_cistern ? __("Remove Cistern") : __("Add Cistern");
			frm.add_custom_button(
				cistern_label,
				() => {
					// We define the fields array based on the current state
					let fields = [
						{
							fieldname: "date",
							fieldtype: "Date",
							label: __("Operation Date"),
							default: frappe.datetime.nowdate(),
							reqd: 1,
						},
						{
							fieldname: "description",
							fieldtype: "Small Text",
							label: __("Reason/Notes"),
							reqd: 1,
						},
					];

					// If adding a cistern, we inject the capacity field at index 1
					if (!frm.doc.has_cistern) {
						fields.splice(1, 0, {
							fieldname: "capacity",
							fieldtype: "Float",
							label: __("Cistern Capacity (m³)"),
							reqd: 1,
						});
					}

					frappe.prompt(
						fields,
						(data) => {
							data.has_cistern = frm.doc.has_cistern ? 0 : 1;
							frm.events.call_update_method(frm, "Cistern", data);
						},
						cistern_label,
					);
				},
				__("Actions"),
			);

			// ACTION: Billing Basis Change
			let billing_label =
				frm.doc.billing_basis === "Flat Rate"
					? __("Install Meter")
					: __("Set to Flat Rate");
			frm.add_custom_button(
				billing_label,
				() => {
					let fields = [
						{
							fieldname: "date",
							fieldtype: "Date",
							label: __("Installation Date"),
							default: frappe.datetime.nowdate(),
							reqd: 1,
						},
					];

					// If moving to Metered, we inject meter fields
					if (frm.doc.billing_basis === "Flat Rate") {
						fields.push({
							fieldname: "meter_id",
							fieldtype: "Data",
							label: __("Meter ID"),
							reqd: 1,
						});
						fields.push({
							fieldname: "start_reading",
							fieldtype: "Float",
							label: __("Initial Reading"),
							reqd: 1,
						});
					}

					fields.push({
						fieldname: "description",
						fieldtype: "Small Text",
						label: __("Justification/Reason"),
						reqd: 1,
					});

					frappe.prompt(
						fields,
						(data) => {
							data.billing_basis =
								frm.doc.billing_basis === "Flat Rate" ? "Metered" : "Flat Rate";
							frm.events.call_update_method(frm, "Billing", data);
						},
						billing_label,
					);
				},
				__("Actions"),
			);

			// ACTION: Status Management
			frm.add_custom_button(
				__("Update Status"),
				() => {
					let options = ["Suspended", "Closed"];
					if (frm.doc.status === "Suspended") options = ["Active", "Closed"];

					frappe.prompt(
						[
							{
								fieldname: "new_status",
								fieldtype: "Select",
								label: __("New Status"),
								options: options,
								reqd: 1,
							},
							{
								fieldname: "date",
								fieldtype: "Date",
								label: __("Effective Date"),
								default: frappe.datetime.nowdate(),
								reqd: 1,
							},
							{
								fieldname: "description",
								fieldtype: "Small Text",
								label: __("Reason/Details"),
								reqd: 1,
							},
						],
						(data) => {
							frm.events.call_update_method(frm, "Status", data);
						},
						__("Change Contract Status"),
					);
				},
				__("Actions"),
			);
		}

		// 3. UI Feedback for Terminal States
		if (terminal_statuses.includes(frm.doc.status)) {
			frm.set_intro(
				__("This contract is {0}. No further actions can be performed.", [frm.doc.status]),
				"red",
			);
		}
	},

	premises: function (frm) {
		// Duplicity check logic
		if (frm.doc.premises) {
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Service Contract",
					filters: {
						premises: frm.doc.premises,
						status: "Active",
						docstatus: ["<", 2],
						name: ["!=", frm.doc.name || ""],
					},
					fieldname: "name",
				},
				callback: function (r) {
					if (r.message && r.message.name) {
						let msg = __(
							"The premises {0} is already linked to active contract {1}.",
							[frm.doc.premises, r.message.name],
						);
						frappe.msgprint({
							title: __("Duplicate Detected"),
							indicator: "red",
							message: msg,
						});
						frm.set_value("premises", "");
					}
				},
			});
		}
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
	},

	call_update_method: function (frm, type, data) {
		frappe.call({
			method: "qota.billing.doctype.service_contract.service_contract.update_contract_property",
			args: { contract_id: frm.doc.name, update_type: type, data: data },
			freeze: true,
			callback: function (r) {
				if (!r.exc) {
					frm.reload_doc();
					frappe.show_alert({
						message: __("Contract updated successfully"),
						indicator: "green",
					});
				}
			},
		});
	},
});
