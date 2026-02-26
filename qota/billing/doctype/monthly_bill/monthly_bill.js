// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Monthly Bill", {
    onload(frm) {  
        frm.set_query("service_contract", function () {
            return {
                query: "qota.governance.doctype.service_contract.service_contract.service_contract_query",
                filters: { docstatus: 1, status: "Active" },
            };
        });
    },
    refresh(frm) {
        // UI Helper for premises description
        if (window.qota && qota.utils && qota.utils.set_premises_description) {
            qota.utils.set_premises_description(frm);
        }

        // Add a button to manually trigger breakdown calculation if in Draft
        if (frm.doc.docstatus === 0 && frm.doc.service_contract) {
            frm.add_custom_button(__('Calculate Breakdown'), () => {
                frm.save();
            }, __('Actions'));
        }
    },

    fiscal_month(frm) {
        set_service_period(frm);
    },

    fiscal_year(frm) {
        set_service_period(frm);
    },

    premises(frm) {
        if (window.qota && qota.utils && qota.utils.set_premises_description) {
            qota.utils.set_premises_description(frm);
        }
    }
});

/**
 * Automatically sets the start_date and end_date based on 
 * the selected Fiscal Month and Fiscal Year.
 */
var set_service_period = function(frm) {
    if (frm.doc.fiscal_month && frm.doc.fiscal_year) {
        // We assume the linked "Billing Year" name is the year numeric value (e.g., "2026")
        // If not, we fetch it from the linked document.
        const year = frm.doc.fiscal_year;
        const month_map = {
            "January": 0, "February": 1, "March": 2, "April": 3, "May": 4, "June": 5,
            "July": 6, "August": 7, "September": 8, "October": 9, "November": 10, "December": 11
        };
        const month_index = month_map[frm.doc.fiscal_month];

        if (month_index !== undefined) {
            // Calculate first day
            const start_date = frappe.datetime.obj_to_str(new Date(year, month_index, 1));
            // Calculate last day (day 0 of next month is the last day of current month)
            const end_date = frappe.datetime.obj_to_str(new Date(year, month_index + 1, 0));

            frm.set_value("start_date", start_date);
            frm.set_value("end_date", end_date);
        }
    }
}