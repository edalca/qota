frappe.listview_settings["Monthly Bill"] = {
	onload: function (listview) {
		listview.premises_data = {};

		listview.page.add_inner_button(__("Add Missing Bills"), function () {
			show_missing_bills_dialog();
		});
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

			if (!data) {
				return `<span class="text-muted">${val}...</span>`;
			}
			const html = `
                        <div>
                            <span><b>${val}</b></span>
                            <small>${__("Block: {0} House: {1}", [data.block, data.house_number])}</small>
                        </div>
                      `;
			return html;
		},
	},
};

function show_missing_bills_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Missing Bills"),
		fields: [
			{
				fieldname: "billing_year",
				fieldtype: "Link",
				label: __("Billing Year"),
				options: "Billing Year",
				reqd: 1,
				get_query: () => ({ filters: { is_closed: 1 } }),
			},
			{
				fieldname: "contract",
				fieldtype: "Link",
				label: __("Service Contract"),
				options: "Service Contract",
				reqd: 1,
				get_query: () => ({ filters: { docstatus: 1 } }),
				onchange() {
					const contract = dialog.get_value("contract");
					if (!contract) {
						dialog.set_value("full_name", "");
						dialog.set_value("premises", "");
						dialog.set_df_property("premises", "description", "");
						return;
					}
					frappe.db.get_value(
						"Service Contract",
						contract,
						["full_name", "premises"],
						(r) => {
							dialog.set_value("full_name", r.full_name || "");
							dialog.set_value("premises", r.premises || "");
							if (r.premises) {
								frappe.db.get_value(
									"Premises",
									r.premises,
									["sector", "block", "house_number"],
									(p) => {
										const desc = `
                                            <div style="margin-top:4px;padding:5px;background:#f8f9fa;border-left:3px solid #3498db;">
                                                <b style="color:#2980b9;">${__("Location")}:</b>
                                                ${__("Block")} ${p.block || "—"},
                                                ${__("House Number")} ${p.house_number || "—"}
                                            </div>`;
										dialog.set_df_property("premises", "description", desc);
									},
								);
							}
						},
					);
				},
			},
			{ fieldname: "col1", fieldtype: "Column Break" },
			{
				fieldname: "full_name",
				fieldtype: "Data",
				label: __("Subscriber Name"),
				read_only: 1,
			},

			{
				fieldname: "premises",
				fieldtype: "Link",
				label: __("Premises"),
				options: "Premises",
				read_only: 1,
			},
			{ fieldname: "sec1", fieldtype: "Section Break", label: __("Missing Periods") },
			{
				fieldname: "periods_html",
				fieldtype: "HTML",
				options: `<div id="missing-periods-container"><p class="text-muted">${__("Select a contract and billing year, then click Search.")}</p></div>`,
			},
		],
		primary_action_label: __("Generate Selected"),
		primary_action(values) {
			const checked = [];
			dialog.wrapper.find(".period-checkbox:checked").each(function () {
				checked.push(JSON.parse($(this).attr("data-period")));
			});

			if (!checked.length) {
				frappe.msgprint(__("Select at least one period to generate."));
				return;
			}

			frappe.call({
				method: "qota.billing.utils.generate_bills_for_periods",
				args: { contract: values.contract, periods: checked },
				freeze: true,
				freeze_message: __("Generating bills..."),
				callback(r) {
					frappe.msgprint(r.message);
					dialog.hide();
					cur_list.refresh();
				},
			});
		},
	});

	// Search button
	dialog.add_custom_action(__("Search"), function () {
		const values = dialog.get_values(true);
		if (!values.contract || !values.billing_year) {
			frappe.msgprint(__("Select a Contract and Billing Year before searching."));
			return;
		}

		frappe.db.get_value("Billing Year", values.billing_year, "year_name", (r) => {
			const yr = r.year_name;
			const from_date = `${yr}-01-01`;
			const to_date = `${yr}-12-31`;

			frappe.call({
				method: "qota.billing.utils.get_missing_periods_for_contract",
				args: { contract: values.contract, from_date, to_date },
				callback(r) {
					const container = dialog.wrapper.find("#missing-periods-container");
					const periods = r.message || [];

					if (!periods.length) {
						container.html(
							`<p class="text-muted">${__("No missing periods found for this range.")}</p>`,
						);
						return;
					}

					let html = `
                    <div style="margin-bottom:8px;">
                        <a href="#" id="check-all-periods">${__("Select All")}</a>
                        &nbsp;|&nbsp;
                        <a href="#" id="uncheck-all-periods">${__("Deselect All")}</a>
                    </div>
                    <table class="table table-bordered table-sm" style="font-size:13px;">
                        <thead><tr>
                            <th style="width:40px;"></th>
                            <th>${__("Period")}</th>
                            <th>${__("Start")}</th>
                            <th>${__("End")}</th>
                        </tr></thead>
                        <tbody>
                `;

					periods.forEach((p) => {
						html += `<tr>
                        <td><input type="checkbox" class="period-checkbox" checked
                            data-period='${JSON.stringify(p)}'></td>
                        <td><strong>${p.period}</strong></td>
                        <td>${p.start_date}</td>
                        <td>${p.end_date}</td>
                    </tr>`;
					});

					html += `</tbody></table>`;
					container.html(html);

					container.find("#check-all-periods").on("click", (e) => {
						e.preventDefault();
						container.find(".period-checkbox").prop("checked", true);
					});
					container.find("#uncheck-all-periods").on("click", (e) => {
						e.preventDefault();
						container.find(".period-checkbox").prop("checked", false);
					});
				},
			});
		}); // end get_value
	});

	dialog.show();
}
