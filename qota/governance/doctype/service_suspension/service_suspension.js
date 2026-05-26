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
        
        // 2. Estado inicial de los filtros y bloqueos
        frm.events.filter_reasons(frm);
        frm.events.handle_maintenance_lock(frm);
    },

    refresh(frm) {
        // Helper para la descripción de predios
        if (window.qota && qota.utils && qota.utils.set_premises_description) {
            qota.utils.set_premises_description(frm);
        }

        // Botón de ejecución técnica solo para órdenes enviadas (Scheduled)
        if (frm.doc.docstatus === 1 && frm.doc.status === 'Scheduled') {
            frm.add_custom_button(__('Confirm Technical Cut'), function() {
                frm.events.open_execution_dialog(frm);
            }, __('Actions'));
        }
    },

    suspension_type: function(frm) {
        if (frm.doc.suspension_type === "By Request") {
            // Seteo automático para solicitud del abonado
            frm.set_value("reason", "Subscriber Request");
            frm.set_df_property("reason", "read_only", 1);
        } else {
            frm.set_df_property("reason", "read_only", 0);
            if (frm.doc.reason === "Subscriber Request") {
                frm.set_value("reason", ""); 
            }
        }
        frm.events.filter_reasons(frm);
        frm.events.handle_maintenance_lock(frm);
    },

    reason: function(frm) {
        frm.events.handle_maintenance_lock(frm);
    },

    filter_reasons: function(frm) {
        let options = [];
        if (frm.doc.suspension_type === "Administrative") {
            options = ["Arrears", "Fraud / Bypass", "Sanction", "Maintenance", "Other"];
        } else if (frm.doc.suspension_type === "By Request") {
            options = ["Subscriber Request"];
        }
        frm.set_df_property("reason", "options", options);
    },

    handle_maintenance_lock: function(frm) {
        /**
         * Si es Mantenimiento, la fecha efectiva DEBE ser la fecha de hoy/posting.
         * No permitimos mantenimiento retroactivo.
         */
        if (frm.doc.reason === "Maintenance") {
            // Extraer solo la parte de la fecha de posting_date (que es Datetime)
            let date_part = frm.doc.posting_date ? frm.doc.posting_date.split(" ")[0] : frappe.datetime.nowdate();
            
            frm.set_value("effective_date", date_part);
            frm.set_df_property("effective_date", "read_only", 1);
            
            frappe.show_alert({
                message: __("Maintenance mode: Effective Date locked to Posting Date."),
                indicator: 'orange'
            }, 3);
        } else {
            // Para otros motivos, dejamos que el usuario decida la fecha (ej. el caso de Enero)
            frm.set_df_property("effective_date", "read_only", 0);
        }
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