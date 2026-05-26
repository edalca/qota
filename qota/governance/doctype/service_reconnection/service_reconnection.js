// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Reconnection", {
    onload(frm) {
        frm.set_query("service_contract", () => ({
            filters: { status: "Suspended" }
        }));
    },

    service_contract(frm) {
        if (!frm.doc.service_contract) return;

        frappe.db.get_list("Service Suspension", {
            filters: {
                service_contract: frm.doc.service_contract,
                status: "Executed",
                docstatus: 1
            },
            fields: ["name", "suspension_type", "reason"],
            order_by: "creation desc",
            limit: 1
        }).then(res => {
            if (!res || !res.length) {
                frappe.show_alert({
                    message: __("No executed suspension found for this contract."),
                    indicator: "red"
                });
                frm.set_value("service_suspension", null);
                return;
            }
            frm.set_value("service_suspension", res[0].name);
            frm.events.apply_fee_logic(frm, res[0]);
        });
    },

    apply_fee_logic(frm, suspension) {
        let is_free = suspension.suspension_type === "By Request" || suspension.reason === "Maintenance";
        if (is_free) {
            frm.set_value("reconnection_fee", 0);
            frm.set_df_property("reconnection_fee", "read_only", 1);
            frappe.show_alert({
                message: __("Free reconnection ({0}). Field locked.", [__(suspension.reason)]),
                indicator: "green"
            });
        } else {
            frm.set_df_property("reconnection_fee", "read_only", 0);
            frappe.db.get_single_value("Billing Settings", "reconnection_fee_item")
                .then(fee => frm.set_value("reconnection_fee", fee || 0));
        }
    },

    refresh(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.status === "Paid") {
            frm.add_custom_button(__("Confirm Technical Reconnection"), () => {
                frm.events.open_reconnection_dialog(frm);
            }, __("Actions"));
        }
    },

    open_reconnection_dialog(frm) {
        let fields = [
            {
                label: __("Execution Date"),
                fieldname: "execution_date",
                fieldtype: "Date",
                default: frappe.datetime.nowdate(),
                reqd: 1
            }
        ];

        if (frm.doc.billing_basis === "Metered") {
            fields.push({
                label: __("Initial Meter Reading"),
                fieldname: "initial_reading",
                fieldtype: "Float",
                reqd: 1
            });
        }

        let d = new frappe.ui.Dialog({
            title: __("Technical Restoration"),
            fields: fields,
            primary_action_label: __("Restore Service"),
            primary_action(values) {
                frm.call("execute_reconnection_logic", {
                    initial_reading: values.initial_reading || 0,
                    execution_date: values.execution_date
                }).then(() => {
                    d.hide();
                    frm.reload_doc();
                });
            }
        });
        d.show();
    }
});
