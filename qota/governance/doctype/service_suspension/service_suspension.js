// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Suspension", {
    onload(frm) {
        frm.set_query("service_contract", function() {
           return {
                query: "qota.governance.doctype.service_contract.service_contract.service_contract_query",
                filters: { docstatus: 1, status: "Active" },
            };
        });
         frm.events.filter_reasons(frm);
    },
    refresh(frm) {
        if (window.qota && qota.utils && qota.utils.set_premises_description) {
            qota.utils.set_premises_description(frm);
        }
        if (frm.doc.docstatus === 1 && frm.doc.status === 'Scheduled') {
            frm.add_custom_button(__('Confirm Technical Cut'), function() {
                frm.events.open_execution_dialog(frm);
            }, __('Actions'));
        }
    },
    suspension_type: function(frm) {
        if (frm.doc.suspension_type === "By Request") {
            // Seteo automático y limpieza de filtros
            frm.set_value("reason", "Subscriber Request");
            frm.set_df_property("reason", "read_only", 1);
        } else {
            frm.set_df_property("reason", "read_only", 0);
            frm.set_value("reason", ""); // Limpiar para que elija una razón admin
        }
        frm.events.filter_reasons(frm);
    },
    filter_reasons: function(frm) {
        // Limitamos las opciones del Select dinámicamente
        let options = [];
        if (frm.doc.suspension_type === "Administrative") {
            options = ["Arrears", "Fraud / Bypass", "Sanction", "Maintenance", "Other"];
        } else if (frm.doc.suspension_type === "By Request") {
            options = ["Subscriber Request"];
        }
        frm.set_df_property("reason", "options", options);
    },
    premises(frm) {
        if (window.qota && qota.utils && qota.utils.set_premises_description) {
            qota.utils.set_premises_description(frm);
        }

    },
    open_execution_dialog: function(frm) {
        /*
        Captures technical data from the field.
        */
        let fields = [{
            label: __('Execution Date'),
            fieldname: 'reading_date',
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
                // Llamamos a nuestra función personalizada de lógica
                frm.call('execute_suspension_logic', {
                    final_reading: values.final_reading || 0,
                    reading_date: values.reading_date
                }).then(() => {
                    d.hide();
                    frm.reload_doc();
                });
            }
        });
        d.show();
    }
});
