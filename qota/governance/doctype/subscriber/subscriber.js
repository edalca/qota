// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Subscriber", {
	refresh: function (frm) {
		frm.set_query("legal_representative", function () {
			return { filters: { subscriber_type: "Natural Person" } };
		});
		handle_id_logic(frm);
	},

	subscriber_type: function (frm) {
		handle_id_logic(frm);
	},

	id_type: function (frm) {
		handle_id_logic(frm);
	},

	id_number: function (frm) {
		if (frm.doc.id_number && frm.doc.id_number.includes(" ")) {
			frm.set_value("id_number", "");
			frappe.msgprint({
				title: __("Invalid Input"),
				indicator: "red",
				message: __("Spaces are not allowed in the ID Number."),
			});
		}
	},
});

function handle_id_logic(frm) {
	// 1. Dynamic Options for id_type
	if (frm.doc.subscriber_type === "Juridical Person") {
		frm.set_df_property("id_type", "options", ["RTN"]);
		if (frm.doc.id_type !== "RTN") frm.set_value("id_type", "RTN");
	} else {
		frm.set_df_property("id_type", "options", ["DNI", "Passport", "Residence Card"]);
		if (frm.doc.id_type === "RTN") frm.set_value("id_type", "DNI");
	}

	// 2. Automated checks for Nationality and Residency
	if (frm.doc.id_type === "DNI") {
		frm.set_value("is_honduran", 1);
		frm.set_value("is_resident", 1);
		frm.set_df_property("id_number", "max_length", 13);
	} else if (frm.doc.id_type === "Residence Card") {
		frm.set_value("is_honduran", 0);
		frm.set_value("is_resident", 1);
		frm.set_df_property("id_number", "max_length", 20);
	} else if (frm.doc.id_type === "RTN") {
		frm.set_value("is_honduran", 0);
		frm.set_value("is_resident", 0);
		frm.set_df_property("id_number", "max_length", 14);
	} else {
		// Passport
		frm.set_value("is_honduran", 0);
		frm.set_value("is_resident", 0);
		frm.set_df_property("id_number", "max_length", 20);
	}
}
