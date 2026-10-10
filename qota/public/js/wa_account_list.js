// The document name is the junta name, so the extra ID column would repeat it.
// Status is the indicator column. List View Settings puts it after the phone.
frappe.listview_settings["WA Account"] = {
	hide_name_column: true,
	get_indicator(doc) {
		if (doc.status === "Active") {
			return [__("Active"), "green", "status,=,Active"];
		}
		if (doc.status === "Inactive") {
			return [__("Inactive"), "red", "status,=,Inactive"];
		}
	},
};
