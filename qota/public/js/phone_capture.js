// Shared telephone capture. Only explicit user edits change stored telephone values.
frappe.provide("qota.phone_capture");
qota.phone_capture = {
	async setup(frm, fields) {
		const response = await frappe.call({
			method: "qota.governance.phone_capture.capture_options", type: "POST",
			args: { doctype: frm.doctype },
		});
		const options = response.message;
		frm._qota_default_phone_region = options.default_region;
		frm._qota_capture_started_empty = !frm.doc[fields.legacy] && !frm.doc[fields.national];
		frm.set_df_property(fields.region, "options", [{ value: "", label: "" }, ...options.regions]);
		if (frm.is_new() && !frm.doc[fields.region] && !frm.doc[fields.national] && !frm.doc[fields.legacy] && options.default_region) {
			await frm.set_value(fields.region, options.default_region);
		}
		const control = frm.fields_dict[fields.national];
		if (control && control.$input) {
			control.$input.attr({ inputmode: "numeric", pattern: "[0-9]*" });
			control.$input.off("beforeinput.qota-phone paste.qota-phone")
				.on("beforeinput.qota-phone", (event) => {
					const data = event.originalEvent.data;
					if (data && /[^0-9]/.test(data)) event.preventDefault();
				}).on("paste.qota-phone", (event) => {
					const value = event.originalEvent.clipboardData.getData("text");
					if (/[^0-9]/.test(value)) {
						event.preventDefault();
						frappe.msgprint(__("Use ASCII digits only in the national number."));
					}
				});
		}
	},
	async warning(frm, fields) {
		if (frm.is_new()) return;
		const { message } = await frappe.call({
			method: "qota.governance.phone_capture.inspect_capture", type: "POST",
			args: { doctype: frm.doctype, name: frm.docname },
		});
		frm.dashboard.clear_headline();
		if (message.status === "Invalid") {
			const text = message.reason_code === "missing_region"
				? __("This historical telephone has no country or region. Select a region and correct the number, or clear the telephone before saving.")
				: __("The telephone number is not valid for the selected country. Correct the number or leave the field empty to continue.");
			frm.dashboard.set_headline_alert(text, "orange");
		}
		if (frm.doc[fields.legacy] && !frm.doc[fields.national]) {
			frm.add_custom_button(__("Clear Telephone"), () => {
				frm.set_value({ [fields.legacy]: "", [fields.national]: "", [fields.e164]: "" });
			});
		}
	},
	async preview(frm, fields) {
		const national = frm.doc[fields.national];
		if (national && !frm.doc[fields.region] && (!frm.doc[fields.legacy] || (fields.legacy === fields.national && frm._qota_capture_started_empty)) && frm._qota_default_phone_region) {
			await frm.set_value(fields.region, frm._qota_default_phone_region);
		}
		const region = frm.doc[fields.region];
		if (!national || !region) return;
		const { message } = await frappe.call({
			method: "qota.governance.phone_capture.preview_capture", type: "POST",
			args: { doctype: frm.doctype, region, national },
		});
		if (national !== frm.doc[fields.national] || region !== frm.doc[fields.region]) return;
		frm.set_df_property(fields.national, "description", message.status === "Valid"
			? __("International preview: {0}", [message.e164])
			: __("The telephone number is not valid for the selected country. Correct the number or leave the field empty to continue."));
	},
};
