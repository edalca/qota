// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on('Payment Receipt', {
    setup: function (frm) {
        frm.set_query("service_contract", function () {
            return {
                query: "qota.billing.doctype.service_contract.service_contract.contract_search",
                filters: { docstatus: 1, status: "Active" },
            };
        });
    },

    /**
     * Initialization and UI restrictions.
     */
    refresh: function (frm) {
        // Utils from premises
        if (window.qota && qota.utils && qota.utils.set_premises_description) {
            qota.utils.set_premises_description(frm);
        }
        frm.get_field("payment_items").grid.cannot_add_rows = true;
        frm.get_field("advance_items").grid.cannot_add_rows = true;

        // 2. Action buttons and math update
        add_action_buttons(frm);
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
                        row.is_mandatory = d.is_mandatory;

                        let time_label = d.days_diff < 0
                            ? ` (OVERDUE: ${Math.abs(d.days_diff)} days)`
                            : ` (Due in ${d.days_diff} days)`;
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
        frm.clear_table("advance_items");
        frm.set_value("current_debt", 0);

        if (frm.doc.service_contract) {
            frm.trigger("load_all_pending_debts");
        } else {
            frm.trigger("calculate_totals");
        }
    },
    /**
     * Update totals when amount received or table items change.
     */
    amount_paid: function (frm) { frm.trigger("calculate_totals"); },
    /**
     * MASTER TOTAL CALCULATION (Using your real JSON fields)
     */
    calculate_totals: function (frm) {
        let total_general = 0;

        // Sumar Deudas Pendientes
        (frm.doc.payment_items || []).forEach(item => {
            total_general += flt(item.amount);
        });

        // Sumar Adelantos de Meses
        (frm.doc.advance_items || []).forEach(item => {
            total_general += flt(item.amount);
        });

        // Aplicamos el valor a ambos campos: lo que debe y lo que paga
        frm.set_value("total_to_pay", total_general);
        frm.set_value("amount_paid", total_general);

        // El saldo sobrante siempre será 0 porque el pago es exacto a lo seleccionado
        frm.set_value("unallocated_amount", 0);
    },
});

// --- ADVANCE DIALOG LOGIC ---

function add_action_buttons(frm) {
    if (frm.is_new() || frm.doc.docstatus === 0) {
        frm.add_custom_button(__("Add Monthly Advances"), () => {
            if (!frm.doc.service_contract) {
                frappe.msgprint(__("Select a Service Contract first."));
                return;
            }

            let d = new frappe.ui.Dialog({
                title: __('Generate Monthly Advances'),
                fields: [
                    { label: __('Months'), fieldname: 'qty', fieldtype: 'Int', default: 1, reqd: 1 },
                    { fieldtype: 'HTML', fieldname: 'preview_html' }
                ],
                primary_action_label: __('Add to Receipt'),
                primary_action(values) {
                    if (d.advances_data) {
                        apply_advances_to_form(frm, d.advances_data);
                    }
                    d.hide();
                }
            });

            d.show();

            let $qty_input = d.get_field('qty').$input;
            let timer = null;
            $qty_input.on('input', () => {
                clearTimeout(timer);
                timer = setTimeout(() => { update_preview(d, frm); }, 450);
            });

            update_preview(d, frm);
        }, __("Actions"));
    }
}

function update_preview(d, frm) {
    let qty = d.get_value('qty');
    if (!qty || qty <= 0) return;

    frappe.call({
        method: "qota.billing.doctype.payment_receipt.payment_receipt.get_next_billing_advances",
        args: { contract_name: frm.doc.service_contract, qty: qty },
        callback: function (r) {
            if (r.message) {
                d.advances_data = r.message;
                let html = `
                    <div style="margin-top: 15px;">
                        <table class="table table-bordered table-condensed">
                            <thead><tr class="text-muted"><th>${__('Period')}</th><th class="text-right">${__('Amount')}</th></tr></thead>
                            <tbody>
                                ${r.message.map(adv => `
                                    <tr><td>${__(adv.month_name)} ${adv.year}</td><td class="text-right">${format_currency(adv.rate)}</td></tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>`;
                d.get_field('preview_html').$wrapper.html(html);
            }
        }
    });
}

function apply_advances_to_form(frm, advances) {
    frm.clear_table("advance_items");
    advances.forEach(adv => {
        let row = frm.add_child("advance_items");
        row.payment_concept = "Monthly Fee";
        row.amount = adv.rate;
        row.description = __("Advance: {0} {1}", [__(adv.month_name), adv.year]);
        row.billing_month = adv.month_num;
        row.billing_year = adv.year;
    });
    frm.refresh_field("advance_items");
    frm.trigger("calculate_totals");
}

