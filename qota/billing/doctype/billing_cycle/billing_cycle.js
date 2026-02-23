// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on('Billing Cycle', {
    onload: function (frm) {
        /*
        Listen to background process signals to refresh the UI 
        when the mass billing batch is finished.
        */
        // Escuchar cuando el proceso en segundo plano termina para refrescar la pantalla
        frappe.realtime.on("billing_cycle_finished", (data) => {
            if (data.name === frm.doc.name) {
                frm.reload_doc();
                frappe.msgprint({
                    title: __('Process Completed'),
                    indicator: 'green',
                    message: data.message
                });
            }
        });
    },

    refresh: function (frm) {
        // Mostrar mensaje de advertencia si el proceso está en cola (background)
        if (frm.doc.status === "Queue") {
            frm.set_intro(__('This cycle is currently being processed in the background.'), 'orange');
            // BOTÓN DE EMERGENCIA: Permite resetear el estado si el proceso se queda pegado
            frm.add_custom_button(__('Reset to Draft'), function () {
                frappe.confirm(__('Are you sure you want to reset the status? Only do this if the process is clearly stuck.'), () => {
                    frm.call('reset_status').then(() => {
                        frm.reload_doc();
                        frappe.show_alert({ message: __('Status reset successfully'), indicator: 'green' });
                    });
                });
            }, __('Actions'));
        }
        if (frm.doc.docstatus === 1 && frappe.user_roles.includes("Administrator")) {
            frm.add_custom_button(__('Update All Rates'), function () {
                frappe.confirm(
                    __('This will cancel and regenerate all UNPAID bills for this cycle with current rates. Continue?'),
                    () => {
                        frm.call('reprocess_cycle_bills').then(() => {
                            frm.reload_doc();
                        });
                    }
                );
            }, __('Actions'));
        }
        // Botón para ejecutar el diagnóstico (Simulación)
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Get Diagnostics'), function () {
                frm.events.run_diagnostics(frm);
            }, __('Actions'));
        }

        // Botón para ver las facturas ya generadas
        if (frm.doc.status === "Completed") {
            frm.add_custom_button(__('View Generated Bills'), function () {
                frappe.set_route('List', 'Monthly Bill', {
                    'billing_cycle': frm.doc.name
                });
            }, __('View'));
        }
    },

    after_save: function (frm) {
        // Ejecutar diagnóstico automáticamente después de guardar en borrador
        if (frm.doc.docstatus === 0) {
            frm.events.run_diagnostics(frm);
        }
    },

    fiscal_month: function (frm) {
        // Recalcular fechas del ciclo al cambiar el mes
        calculate_cycle_dates(frm);
    },

    fiscal_year: function (frm) {
        // Recalcular fechas del ciclo al cambiar el año
        calculate_cycle_dates(frm);
    },

    run_diagnostics: function (frm) {
        /*
        Triggers the server-side simulation and reloads the document
        to show issues in the child table.
        */
        // Llama al servidor para ejecutar la simulación y recarga los datos en la tabla 'issues'
        frappe.call({
            method: "get_billing_diagnostics",
            doc: frm.doc,
            freeze: true,
            freeze_message: __("Identifying billing gaps..."),
            callback: function (r) {
                // Recargamos el documento para que la tabla 'issues' se pinte con los resultados
                frm.reload_doc();

                if (frm.doc.issues && frm.doc.issues.length > 0) {
                    frappe.msgprint({
                        title: __('Diagnostics Finished'),
                        indicator: 'orange',
                        message: __('Found {0} contracts with issues. Check the Execution Issues section.', [frm.doc.issues.length])
                    });
                } else {
                    frappe.show_alert({
                        message: __('No issues detected. Ready for billing.'),
                        indicator: 'green'
                    });
                }
            }
        });
    }
});

/**
 * Automatic Date Logic based on ERSAPS settings.
 */
function calculate_cycle_dates(frm) {
    // Lógica para calcular automáticamente start_date y end_date según el mes/año fiscal
    if (frm.doc.fiscal_month && frm.doc.fiscal_year) {
        frappe.db.get_single_value('Billing Settings', 'cycle_start_day')
            .then(start_day => {
                if (!start_day) start_day = 1;

                frappe.db.get_value('Billing Year', frm.doc.fiscal_year, 'year_name')
                    .then(r => {
                        if (r && r.message && r.message.year_name) {
                            let year = parseInt(r.message.year_name);
                            let month_map = {
                                "January": 0, "February": 1, "March": 2, "April": 3, "May": 4, "June": 5,
                                "July": 6, "August": 7, "September": 8, "October": 9, "November": 10, "December": 11
                            };
                            let month_idx = month_map[frm.doc.fiscal_month];
                            let start_date, end_date;

                            if (start_day == 1) {
                                start_date = new Date(year, month_idx, 1);
                                end_date = new Date(year, month_idx + 1, 0);
                            } else {
                                start_date = new Date(year, month_idx, start_day);
                                end_date = new Date(year, month_idx + 1, start_day - 1);
                            }

                            frm.set_value('start_date', frappe.datetime.obj_to_str(start_date));
                            frm.set_value('end_date', frappe.datetime.obj_to_str(end_date));
                        }
                    });
            });
    }
}