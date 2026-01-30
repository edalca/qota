frappe.listview_settings["Meter Reading"] = {
	onload: function (listview) {
		listview.premises_data = {};
	},

	refresh: function (listview) {
		let premises_ids = listview.data
			.map((d) => d.premises)
			.filter((id) => id && !listview.premises_data[id]);

		if (premises_ids.length > 0) {
			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Premises",
					filters: { name: ["in", premises_ids] },
					fields: ["name", "sector", "block", "house_number"],
				},
				callback: function (r) {
					if (r.message) {
						r.message.forEach((p) => {
							listview.premises_data[p.name] = p;
						});
						listview.render();
					}
				},
			});
		}
	},

	formatters: {
		premises(val, df, doc) {
			const listview = cur_list;
			const data = listview.premises_data ? listview.premises_data[val] : null;

			if (data) {
				const labelSec = __("Sector");
				const labelBlk = __("Block");
				const labelHse = __("House Number");

				return `
                    <div style="line-height: 1.4;">
                        <span>${val}</span><br>
                        <small>
                            ${labelSec} ${data.sector}, ${labelBlk} ${data.block}, ${labelHse} ${data.house_number}
                        </small>
                    </div>
                `;
			}
			return `<span class="text-muted">${val}...</span>`;
		},
	},
};
