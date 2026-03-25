// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Contract", {
	setup: function (frm) {
		// Filter: only active subscribers
		frm.set_query("subscriber", () => {
			return { filters: { status: "Active" } };
		});

		// Filter: only active, non-contracted premises
		frm.set_query("premises", () => {
			return {
				query: "qota.governance.doctype.premises.premises.premises_search",
				filters: { status: "Active", docstatus: 0 },
			};
		});

	},

	refresh: function (frm) {
		// Bloquear campos críticos si el documento ya fue enviado
		const fields_to_lock = [
			"status",
			"billing_basis",
			"meter_id",
			"start_reading",
			"has_cistern",
			"cistern_capacity",
			"service_category",
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
		if (frm.doc.docstatus === 1) {

			// ACTION: View History Log (NUEVO)
			frm.add_custom_button(
				__("View History Log"),
				() => frm.events.show_history_log(frm),
				__("Actions")
			);
		}
		// 2. Actions for Active/Suspended contracts
		// Solo permitimos acciones si NO está cerrado o cancelado
		const terminal_statuses = ["Closed", "Cancelled"];

		if (frm.doc.docstatus === 1 && !terminal_statuses.includes(frm.doc.status)) {
			// ACTION: Cistern Management
			let cistern_label = frm.doc.has_cistern ? __("Remove Cistern") : __("Add Cistern");
			frm.add_custom_button(
				cistern_label,
				() => {
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

			// ACTION: Close Contract (Única acción de estado permitida manual)
			frm.add_custom_button(
				__("Close Contract"),
				() => {
					frappe.prompt(
						[
							{
								fieldname: "date",
								fieldtype: "Date",
								label: __("Closing Date"),
								default: frappe.datetime.nowdate(),
								reqd: 1,
							},
							{
								fieldname: "description",
								fieldtype: "Small Text",
								label: __("Reason for Closing"),
								reqd: 1,
							},
						],
						(data) => {
							// Forzamos el estado a "Closed"
							data.new_status = "Closed";
							frm.events.call_update_method(frm, "Status", data);
						},
						__("Terminate Contract"), // Título del diálogo
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

    show_history_log: function(frm) {
        frappe.db.get_list("Service Contract Log", {
            filters: {
                "service_contract": frm.doc.name
            },
            // Using your exact JSON fields:
            fields: ["operation_date", "change_type", "field_changed", "description", "owner"],
            order_by: "operation_date desc",
            limit: 50
        }).then(logs => {
            if (!logs || logs.length === 0) {
                frappe.msgprint({
                    title: __("Contract History"),
                    indicator: "blue",
                    message: __("No audit records found for this contract.")
                });
                return;
            }

            let html = `
                <table class="table table-bordered table-condensed" style="font-size: 13px;">
                    <thead>
                        <tr class="active">
                            <th style="width: 15%">${__("Op. Date")}</th>
                            <th style="width: 20%">${__("Change Type")}</th>
                            <th style="width: 20%">${__("Field")}</th>
                            <th style="width: 30%">${__("Description")}</th>
                            <th style="width: 15%">${__("User")}</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            logs.forEach(log => {
                // Color mapping based on your Select options
                let label_class = "label-default";
                if (log.change_type === "Status Change") label_class = "label-warning";
                if (log.change_type === "Cistern Update") label_class = "label-info";
                if (log.change_type === "Billing Basis Change") label_class = "label-primary";

                html += `
                    <tr>
                        <td>${frappe.datetime.str_to_user(log.operation_date)}</td>
                        <td><span class="label ${label_class}">${__(log.change_type)}</span></td>
                        <td><code style="font-size: 11px;">${log.field_changed || "-"}</code></td>
                        <td>${log.description || ""}</td>
                        <td><small class="text-muted">${log.owner}</small></td>
                    </tr>
                `;
            });

            html += `</tbody></table>`;

            let d = new frappe.ui.Dialog({
                title: __("Operation Log - {0}", [frm.doc.name]),
                size: "large",
                fields: [
                    {
                        fieldname: "history_html",
                        fieldtype: "HTML",
                        options: html
                    }
                ],
                primary_action_label: __("Close"),
                primary_action() {
                    d.hide();
                }
            });

            d.show();
        });
    },

	call_update_method: function (frm, type, data) {
		frappe.call({
			method: "qota.governance.doctype.service_contract.service_contract.update_contract_property",
			args: { service_contract: frm.doc.name, update_type: type, data: data },
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
