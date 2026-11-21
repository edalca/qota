frappe.listview_settings["Water Issue Report"] = {
    filters: [["status", "=", "Pending"]],
    get_indicator(doc) {
        return doc.status === "Seen" ? [__("Seen"), "green", "status,=,Seen"] : [__("Pending"), "orange", "status,=,Pending"];
    },
};
