// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt


frappe.ui.form.on("Service Reconnection", {
    onload(frm) {
        // Filtrar solo contratos suspendidos
        frm.set_query("service_contract", function () {
            return {
                query: "qota.governance.doctype.service_contract.service_contract.service_contract_query",
                filters: { docstatus: 1, status: "Suspended" },
            };
        });
    },
    service_contract: function (frm) {
        if (frm.doc.service_contract) {
            // Buscamos la última suspensión ejecutada usando get_list (más seguro)
            frappe.db.get_list("Service Suspension", {
                filters: {
                    "service_contract": frm.doc.service_contract,
                    "status": "Executed",
                    "docstatus": 1
                },
                fields: ["suspension_type", "reason"],
                order_by: "creation desc",
                limit: 1
            }).then(res => {
                if (res && res.length > 0) {
                    let r = res[0];
                    let is_free = (r.suspension_type === "By Request" || r.reason === "Maintenance");

                    if (is_free) {
                        frm.set_value("reconnection_fee", 0);
                        frm.set_df_property("reconnection_fee", "read_only", 1); // BLOQUEAR
                        frappe.show_alert({
                            message: __("Free reconnection ({0}). Field locked.", [r.reason]),
                            indicator: 'green'
                        });
                    } else {
                        frm.set_df_property("reconnection_fee", "read_only", 0); // DESBLOQUEAR
                        // Jalamos la tarifa por defecto si se debe cobrar
                        frappe.db.get_single_value("Billing Settings", "default_reconnection_fee")
                            .then(fee => frm.set_value("reconnection_fee", fee || 0));
                    }
                }
            });
        }
    },

    refresh(frm) {
        // Botón técnico: Solo si está pagado (ya sea porque pagó o porque fue gratis)
        if (frm.doc.docstatus === 1 && frm.doc.status === 'Paid') {
            frm.add_custom_button(__('Confirm Technical Reconnection'), () => {
                frm.events.open_reconnection_dialog(frm);
            }, __('Actions'));
        }
    },

    open_reconnection_dialog: function (frm) {
        let fields = [
            {
                label: __('Execution Date'),
                fieldname: 'execution_date',
                fieldtype: 'Date',
                default: frappe.datetime.nowdate(),
                reqd: 1
            }
        ];

        if (frm.doc.billing_basis === "Metered") {
            fields.push({
                label: __('Initial Meter Reading'),
                fieldname: 'initial_reading',
                fieldtype: 'Float',
                reqd: 1
            });
        }

        let d = new frappe.ui.Dialog({
            title: __('Technical Restoration'),
            fields: fields,
            primary_action_label: __('Restore Service'),
            primary_action(values) {
                frm.call('execute_reconnection_logic', {
                    initial_reading: values.initial_reading || 0,
                    execution_date: values.execution_date // <-- Enviamos la fecha
                }).then(() => {
                    d.hide();
                    frm.reload_doc();
                });
            }
        });
        d.show();
    }
});