frappe.provide("qota.utils");

qota.utils = {
	location: function (frm, callback) {
		if (!frm.doc.premises) {
			callback({
				sector: "",
				block: "",
				house_number: "",
			});
			return;
		}

		frappe.db.get_value(
			"Premises",
			frm.doc.premises,
			["sector", "block", "house_number"],
			(r) => {
				callback({
					sector: r?.sector || "",
					block: r?.block || "",
					house_number: r?.house_number || "",
				});
			},
		);
	},

	set_location: function (frm) {
		qota.utils.location(frm, function (location) {
			frm.set_value(
				"location",
				location.sector + ", " + location.block + ", " + location.house_number,
			);
		});
	},

	set_premises_description: function (frm) {
		qota.utils.location(frm, function (location) {
			const description_html = `
                <div style="margin-top: 5px; padding: 5px; background-color: #f8f9fa; border-left: 3px solid #3498db;">
                    <b style="color: #2980b9;">${__("Location")}:</b>
                    ${__("Block")} ${location.block},
                    ${__("House Number")} ${location.house_number}
                </div>
            `;

			frm.set_df_property("premises", "description", description_html);
		});
	},
};
