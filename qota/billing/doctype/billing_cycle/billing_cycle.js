// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on('Billing Cycle', {
    onload: function(frm) {
        // 1. Escuchar la señal del servidor cuando termine el proceso de fondo
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
        // 2. Indicador visual si el proceso está en cola
        if (frm.doc.status === "Queue") {
            frm.set_intro(__('This cycle is currently being processed in the background. Please wait for the "Completed" status.'), 'orange');
        }

        // 3. Ejecutar diagnóstico solo en Borrador
        if (frm.doc.docstatus === 0 && frm.doc.start_date) {
            run_diagnostics(frm);
        }

        // 4. Botón para ver facturas generadas (Solo si ya hay resultados)
        if (frm.doc.status === "Completed") {
            frm.add_custom_button(__('View Generated Bills'), function () {
                frappe.set_route('List', 'Monthly Bill', {
                    'billing_cycle': frm.doc.name
                });
            }, __('View'));
        }
    },

    after_save: function (frm) {
        if (frm.doc.docstatus === 0) {
            run_diagnostics(frm);
        }
    },

    fiscal_month: function (frm) { 
        clear_diagnostics(frm);
        calculate_cycle_dates(frm); 
    },

    fiscal_year: function (frm) { 
        clear_diagnostics(frm);
        calculate_cycle_dates(frm); 
    }
});

/**
 * Llama al diagnóstico masivo y renderiza la tabla agrupada.
 */
function run_diagnostics(frm) {
    frappe.call({
        method: "get_billing_diagnostics",
        doc: frm.doc,
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                let html = `
                    <div class="alert alert-danger" style="margin-bottom: 15px; border-left: 5px solid #d9534f;">
                        <i class="fa fa-exclamation-triangle" style="font-size: 1.2em;"></i> 
                        <strong style="margin-left: 10px;">${__('Continuity Gaps Detected')}</strong>
                        <p style="margin-top: 5px; margin-bottom: 0;">${__('The following contracts will be skipped during processing.')}</p>
                    </div>
                    <div style="max-height: 500px; overflow-y: auto; padding-right: 5px;">`;

                r.message.forEach(group => {
                    html += `
                        <div style="margin-bottom: 15px; border: 1px solid #fbcfe8; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                            <div style="background-color: #fff1f2; padding: 10px; border-bottom: 1px solid #fecdd3; display: flex; justify-content: space-between; align-items: center;">
                                <span style="color: #be123c; font-weight: bold;">
                                    <i class="fa fa-folder-open"></i> ${group.reason}
                                </span>
                                <span class="badge badge-danger" style="font-size: 0.9em; padding: 5px 10px;">
                                    ${group.contracts.length} ${__('Contracts')}
                                </span>
                            </div>
                            <div style="padding: 12px; background-color: #fff;">
                                ${group.contracts.map(c => `
                                    <a href="/app/service-contract/${c}" target="_blank" 
                                       class="btn btn-xs btn-default" 
                                       style="margin: 3px; border: 1px solid #d1d8dd; font-weight: 500;">
                                       ${c} <i class="fa fa-external-link" style="font-size: 8px; margin-left: 4px; color: #8d99a6;"></i>
                                    </a>
                                `).join('')}
                            </div>
                        </div>`;
                });

                html += `</div>
                    <div class="text-muted small" style="margin-top: 10px;">
                        <i class="fa fa-lightbulb-o text-warning"></i> 
                        ${__('Action Required: Create the missing monthly bills for these contracts to clear the alerts.')}
                    </div>`;

                frm.set_df_property('diagnostic_html', 'options', html);
                frm.set_df_property('diagnostics_section', 'hidden', 0);
                frm.refresh_field('diagnostics_section');
                frm.refresh_field('diagnostic_html');
            } else {
                clear_diagnostics(frm);
            }
        }
    });
}

/**
 * Limpieza profunda del área de diagnóstico.
 */
function clear_diagnostics(frm) {
    if (frm.fields_dict.diagnostic_html) {
        frm.fields_dict.diagnostic_html.wrapper.innerHTML = "";
    }
    frm.set_df_property('diagnostic_html', 'options', "");
    frm.set_df_property('diagnostics_section', 'hidden', 1);
    frm.refresh_field('diagnostics_section');
}

/**
 * Lógica automática de fechas.
 */
function calculate_cycle_dates(frm) {
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