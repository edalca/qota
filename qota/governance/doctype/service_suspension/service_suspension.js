// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Suspension", {
    onload(frm) {
        // 1. Filtrar contratos activos usando el query centralizado
        frm.set_query("service_contract", function() {
            return {
                query: "qota.governance.doctype.service_contract.service_contract.service_contract_query",
                filters: { docstatus: 1, status: "Active" },
            };
        });
        
        frm.events.setup_service_fine(frm);
    },

    refresh(frm) {
        // Helper para la descripción de predios
        if (window.qota && qota.utils && qota.utils.set_premises_description) {
            qota.utils.set_premises_description(frm);
        }
        frm.events.setup_service_fine(frm);

        // Botón de ejecución técnica solo para órdenes enviadas (Scheduled)
        if (frm.doc.docstatus === 1 && frm.doc.status === 'Scheduled') {
            frm.add_custom_button(__('Confirm Technical Cut'), function() {
                frm.events.open_execution_dialog(frm);
            }, __('Actions'));
        }
    },

    suspension_type: function(frm) {
        if (frm.doc.suspension_type !== "By Fine" && frm.doc.service_fine) {
            frm.set_value("service_fine", "");
        }
        frm.events.setup_service_fine(frm);
    },

    service_contract: function(frm) {
        frm.events.setup_service_fine(frm);
    },

    setup_service_fine: function(frm) {
        const needs_fine = frm.doc.suspension_type === "By Fine";
        frm.toggle_display("service_fine", needs_fine);
        frm.toggle_reqd("service_fine", needs_fine);
        frm.set_query("service_fine", () => {
            return {
                filters: {
                    service_contract: frm.doc.service_contract || "",
                    docstatus: 1,
                    status: "Unpaid",
                },
            };
        });
    },

    open_execution_dialog: function(frm) {
        let fields = [{
            label: __('Execution Date'),
            fieldname: 'executed_date', // Nombre coincidente con tu JSON
            fieldtype: 'Date',
            default: frappe.datetime.nowdate(),
            reqd: 1
        }];
        
        if (frm.doc.billing_basis === "Metered") {
            fields.push({
                label: __('Final Meter Reading'),
                fieldname: 'final_reading',
                fieldtype: 'Float',
                reqd: 1
            });
        }

        let d = new frappe.ui.Dialog({
            title: __('Technical Confirmation'),
            fields: fields,
            primary_action_label: __('Execute Cut'),
            primary_action(values) {
                frm.call('execute_suspension_logic', {
                    final_reading: values.final_reading || 0,
                    executed_date: values.executed_date
                }).then(() => {
                    d.hide();
                    frappe.show_alert({
                        message: __("Service suspended successfully"),
                        indicator: 'blue'
                    });
                    frm.reload_doc();
                });
            }
        });
        d.show();
    }
});