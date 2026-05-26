// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on('Payment Receipt', {
    setup: function (frm) {
        frm.set_query("service_contract", function () {
            return {
                query: "qota.governance.doctype.service_contract.service_contract.service_contract_query",
                filters: { docstatus: 1, status: ["in", ["Active", "Suspended"]] },
            };
        });
        frm.get_field("payment_items").grid.cannot_add_rows = true;
    },
    /**
     * Initialization and UI restrictions.
     */
    refresh: function (frm) {
        // Utils from premises
        if (window.qota && qota.utils && qota.utils.set_premises_description) {
            qota.utils.set_premises_description(frm);
        }
        if (frm.doc.docstatus === 0) {
            frappe.db.get_value("Service Contract", frm.doc.service_contract, "status").then(r => {
                if (r && r.message && r.message.status !== "Suspended") {
                    frm.add_custom_button(__("Add Monthly Advance"), function () {
                        if (!frm.doc.service_contract) {
                            frappe.msgprint(__("Please select a Service Contract first."));
                            return;
                        }
                        open_advance_dialog(frm);
                    }, __("Actions"));
                }
            });
        }

    },

    premises: function (frm) {
        if (window.qota && qota.utils && qota.utils.set_premises_description) {
            qota.utils.set_premises_description(frm);
        }
    },
    /**
     * Fetch pending debts from the ledger and populate the table.
     */
    load_all_pending_debts: function (frm) {
        if (!frm.doc.service_contract) return;

        frappe.call({
            method: "qota.billing.doctype.payment_receipt.payment_receipt.get_pending_balances",
            args: { contract: frm.doc.service_contract },
            callback: function (r) {
                if (r.message) {
                    // Update header debt info
                    frm.set_value("current_debt", r.message.current_debt);
                    frm.clear_table("payment_items");

                    // Populate existing debts table
                    (r.message.debts || []).forEach(d => {
                        let row = frm.add_child("payment_items");
                        row.payment_concept = d.payment_concept;
                        row.amount = d.amount;
                        row.debt_id = d.debt_id;
                        row.due_date = d.due_date;
                        row.billing_period = d.billing_period;
                        row.balance = d.amount;
                        row.debt_ledger_entry = d.debt_id;

                        let time_label = d.days_diff < 0
                            ? ` (${__("OVERDUE: {0} days", [Math.abs(d.days_diff)])})`
                            : ` (${__("Due in {0} days", [d.days_diff])})`;
                        row.description = `${d.description || ''}${time_label}`;
                    });

                    frm.refresh_field("payment_items");
                    frm.trigger("calculate_totals"); // Updated trigger name
                }
            }
        });
    },

    /**
     * Triggers when Service Contract changes.
     */
    service_contract: function (frm) {
        frm.clear_table("payment_items");
        frm.set_value("current_debt", 0);

        if (frm.doc.service_contract) {
            frm.trigger("load_all_pending_debts");
        } else {
            frm.trigger("calculate_totals");
        }
    },
    /**
     * MASTER TOTAL CALCULATION (Using your real JSON fields)
     */
    calculate_totals: function (frm) {
        let total_to_pay = 0;
        let unallocated_amount = 0;
        // Sumar Deudas Pendientes
        (frm.doc.payment_items || []).forEach(item => {
            if (!item.debt_ledger_entry) {
                unallocated_amount += flt(item.amount);
            }
            total_to_pay += flt(item.amount);
        });
        let total_pending = flt(frm.doc.current_debt || 0) - flt(total_to_pay || 0) + flt(unallocated_amount || 0);
        // Aplicamos el valor a ambos campos: lo que debe y lo que paga
        frm.set_value("total_to_pay", total_to_pay);
        frm.set_value("unallocated_amount", unallocated_amount);
        frm.set_value("total_pending", total_pending);

    },
    payment_items_remove: function (frm, cdt, cdn) {
        console.log("Item removed, recalculating totals...");
    },
});
frappe.ui.form.on('Payment Receipt Item', "payment_items_remove", function (frm, cdt, cdn) {
    frm.trigger("calculate_totals");
});
frappe.ui.form.on('Payment Receipt Item', {
    view_details: function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        if (!row.billing_details) {
            frappe.msgprint({
                title: __('Notice'),
                indicator: 'orange',
                message: __('This item has no detailed breakdown.')
            });
            return;
        }

        try {
            // Parse the hidden JSON
            const details = JSON.parse(row.billing_details);

            // Call the function that creates the dialog (make sure it's defined)
            show_billing_breakdown_dialog(row.billing_period || "Details", details);
        } catch (e) {
            frappe.msgprint(__("Error loading technical details."));
        }
    }
});
/**
 * Abre el diálogo para seleccionar meses de adelanto.
 */
function open_advance_dialog(frm) {
    let d = new frappe.ui.Dialog({
        title: __("Select Months to Advance"),
        fields: [
            {
                fieldname: 'months_html',
                fieldtype: 'HTML'
            }
        ],
        primary_action_label: __("Add to Receipt"),
        primary_action: function () {
            const $wrapper = d.get_field('months_html').$wrapper;
            const selected_indexes = [];

            // Recolectar índices seleccionados
            $wrapper.find('.month-check:checked').each(function () {
                selected_indexes.push($(this).data('index'));
            });

            if (selected_indexes.length > 0) {
                let added_count = 0;

                selected_indexes.forEach(index => {
                    let data = d.months_data[index];

                    // Evitar duplicados por periodo billing_period (MM-YYYY)
                    let exists = (frm.doc.payment_items || []).some(item => item.billing_period === data.billing_period);

                    if (!exists) {
                        let row = frm.add_child('payment_items');
                        row.payment_concept = 'Monthly Fee';
                        row.billing_period = data.billing_period;
                        row.description = data.description;
                        row.amount = data.amount;
                        row.due_date = data.due_date;

                        row.billing_details = JSON.stringify(data.billing_details || []);

                        added_count++;
                    }
                });

                frm.refresh_field('payment_items');
                frm.trigger("calculate_totals");

                if (added_count > 0) {
                    frappe.show_alert({
                        message: __("Added {0} months to the receipt", [added_count]),
                        indicator: 'green'
                    });
                }
            }
            d.hide();
        }
    });

    frm.call('get_next_billing_advances', {
        contract_name: frm.doc.service_contract,
        qty: 12
    }).then(r => {
        if (r.message && r.message.length > 0) {
            d.months_data = r.message;
            render_month_selection_table(d, r.message);
            d.show();
        } else {
            frappe.msgprint(__("No available months found for advances."));
        }
    });
}

/**
 * Renderiza la tabla con Scroll, Diseño Limpio y Botón de Detalle
 */
function render_month_selection_table(d, months) {
    let html = `
        <style>
            .adv-scroll-container {
                max-height: 400px; 
                overflow-y: auto; 
                border: 1px solid #d1d8dd; 
                border-radius: 4px;
            }
            .adv-scroll-container thead th {
                position: sticky; top: 0; background-color: #f8f9fa; z-index: 2;
                box-shadow: inset 0 -1px 0 #d1d8dd;
            }
            .adv-table-row:hover { background-color: #f7fafc; cursor: pointer; }
            .adv-amount { font-weight: bold; font-family: monospace; padding-right: 5px !important; }
            .btn-view-detail { padding: 2px 5px; font-size: 11px; }
        </style>

        <div class="adv-scroll-container">
            <table class="table table-condensed" style="margin-bottom: 0;">
                <thead>
                    <tr class="text-muted">
                        <th class="text-center" style="width: 40px;">✔</th>
                        <th>${__("Period")}</th>
                        <th class="text-right">${__("Amount")}</th>
                    </tr>
                </thead>
                <tbody>
                    ${months.map((m, i) => `
                        <tr class="adv-table-row">
                            <td class="text-center" style="vertical-align: middle;">
                                <input type="checkbox" class="month-check" data-index="${i}">
                            </td>
                            <td>
                                <strong>${m.billing_period}</strong> <br>
                                <span class="text-muted small">${m.description}</span>
                            </td>
                            <td class="text-right" style="vertical-align: middle; white-space: nowrap;">
                                <span class="adv-amount">${format_currency(m.amount)}</span>
                                <button class="btn btn-link btn-view-detail view-breakdown" data-index="${i}">
                                    <i class="fa fa-info-circle text-info"></i>
                                </button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
        <p class="text-muted small text-center" style="margin-top: 10px;">
            <i class="fa fa-info-circle"></i> ${__("Months must be selected in sequential order.")}
        </p>
    `;

    const $wrapper = d.get_field('months_html').$wrapper;
    $wrapper.html(html);

    // --- LÓGICA DE SELECCIÓN SECUENCIAL ---
    $wrapper.find('.month-check').on('change', function () {
        const current_idx = $(this).data('index');
        const is_checked = $(this).is(':checked');
        const $all_checks = $wrapper.find('.month-check');

        if (is_checked) {
            $all_checks.each(function () {
                if ($(this).data('index') < current_idx) $(this).prop('checked', true);
            });
        } else {
            $all_checks.each(function () {
                if ($(this).data('index') > current_idx) $(this).prop('checked', false);
            });
        }
    });

    // --- LÓGICA PARA MOSTRAR EL DIÁLOGO DE DESGLOSE ---
    $wrapper.find('.view-breakdown').on('click', function (e) {
        e.stopPropagation(); // Evita marcar el checkbox al hacer clic en el botón
        const idx = $(this).data('index');
        const m = months[idx];

        // Parseamos el JSON que viene del servidor
        const details = m.billing_details || [];
        show_billing_breakdown_dialog(m.billing_period, details);
    });

    // UX: Clic en la fila activa el checkbox
    $wrapper.find('.adv-table-row').on('click', function (e) {
        if (!$(e.target).is('input') && !$(e.target).closest('button').length) {
            $(this).find('input').click();
        }
    });
}

/**
 * Muestra una ventanita con el desglose de la tarifa (Agua, Cisterna, etc)
 */
function show_billing_breakdown_dialog(period, details) {
    let rows = details.map(d => `
        <tr>
            <td>${d.description}</td>
            <td class="text-right">${format_currency(d.amount)}</td>
        </tr>
    `).join('');

    let html = `
        <table class="table table-bordered table-condensed">
            <thead>
                <tr class="text-muted">
                    <th>${__("Payment Concept")}</th>
                    <th class="text-right">${__("Amount")}</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;

    const d = new frappe.ui.Dialog({
        title: __('Breakdown for {0}', [period]),
        fields: [
            { fieldtype: 'HTML', fieldname: 'html_breakdown' }
        ]
    });

    d.get_field('html_breakdown').$wrapper.html(html);
    d.show();
}