frappe.ui.form.on("Institutional Settings", {
	async onload(frm) {
		const { message } = await frappe.call({ method: "qota.governance.phone_capture.capture_options", type: "POST", args: { doctype: frm.doctype } });
		frm.set_df_property("default_phone_region", "options", [{ value: "", label: "" }, ...message.regions]);
	},
	refresh(frm) {
		frm.page.set_title(__("Governance Settings"));
		if (!frm.office_calendar_editor) {
			frm.office_calendar_editor = new qota.governance.OfficeCalendarEditor(frm);
		}
		frm.office_calendar_editor.refresh();
		frm.add_custom_button(__("Review Historical Telephones"), async () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save the configuration before reviewing historical telephones."));
				return;
			}
			const { message: review } = await frappe.call({ method: "qota.governance.phone_region_assignment.preview_assignment", type: "POST" });
			const summary = __("Region: {0}. Pending: {1}. Valid: {2}. Invalid: {3}.", [review.region, review.eligible, review.valid, review.invalid]);
			if (!review.eligible) {
				frappe.msgprint(summary);
				return;
			}
			frappe.confirm(summary + "<br><br>" + review.warning + "<br><br>" + __("Assign this region to the reviewed historical records?"), async () => {
				const { message: result } = await frappe.call({ method: "qota.governance.phone_region_assignment.apply_assignment", type: "POST", freeze: true, args: { token: review.token, confirmed: 1 } });
				frappe.msgprint(__("Assigned: {0}. Pending: {1}. Original telephone values were preserved.", [result.assigned, result.remaining]));
			});
		});
	},
});

frappe.provide("qota.governance");

qota.governance.OfficeCalendarEditor = class OfficeCalendarEditor {
	static get types() {
		return [
			{ value: "Holiday", label: "Holiday", action: "Register holiday" },
			{ value: "Exceptional Hours", label: "Exceptional Hours", action: "Exceptional Hours" },
			{ value: "Extraordinary Closure", label: "Extraordinary Closure", action: "Extraordinary Closure" },
		];
	}

	static normalize(kind, values) {
		if (!this.types.some((type) => type.value === kind)) {
			frappe.throw(__("Choose an approved calendar exception type."));
		}
		const day = values.exception_date || "";
		// Parse the date components without consulting the browser clock or timezone.
		const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
		const year = match && Number(match[1]);
		const month = match && Number(match[2]);
		const date = match && Number(match[3]);
		const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
		const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
		if (!match || year < 1 || month < 1 || month > 12 || date < 1 || date > days[month - 1]) {
			frappe.throw(__("Institutional dates must be valid dates in YYYY-MM-DD format."));
		}
		const reason = kind === "Holiday" ? "" : (values.internal_reason || "").trim();
		if (kind !== "Holiday" && !reason) {
			frappe.throw(__("Exceptional hours and extraordinary closures require an internal reason."));
		}
		const exception = {
			exception_date: day, exception_type: kind,
			day_status: kind === "Exceptional Hours" ? "Open" : "Closed",
			internal_reason: reason, public_reason: "",
		};
		let interval = null;
		if (kind === "Exceptional Hours") {
			const normalize_time = (value) => {
				const parts = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(value || "");
				if (!parts || Number(parts[1]) > 23 || Number(parts[2]) > 59 || Number(parts[3] || 0) > 59) {
					frappe.throw(__("Office times must be valid local times in H:MM or H:MM:SS format (one or two hour digits)."));
				}
				return `${parts[1].padStart(2, "0")}:${parts[2]}:${parts[3] || "00"}`;
			};
			const start_time = normalize_time(values.start_time);
			const end_time = normalize_time(values.end_time);
			if (start_time >= end_time) {
				frappe.throw(__("Opening time must precede closing time. Overnight intervals are not supported."));
			}
			interval = { exception_date: day, start_time, end_time };
		}
		return { exception, interval };
	}

	constructor(frm) {
		this.frm = frm;
		this.$wrapper = frm.fields_dict.calendar_exceptions_html.$wrapper;
		this.request = 0;
		this.$wrapper.on("click.qota_calendar", "[data-register]", (event) => {
			this.open_dialog(event.currentTarget.dataset.register);
		});
		this.$wrapper.on("click.qota_calendar", "[data-edit]", (event) => {
			const row = this.find(event.currentTarget.dataset.edit);
			if (row) this.open_dialog(row.exception_type, row);
		});
		this.$wrapper.on("click.qota_calendar", "[data-remove]", (event) => {
			const row = this.find(event.currentTarget.dataset.remove);
			if (row) this.confirm_remove(row);
		});
		frm.$wrapper.off("dirty.qota_calendar shown.bs.tab.qota_calendar")
			.on("dirty.qota_calendar", () => this.render())
			.on("shown.bs.tab.qota_calendar", () => this.refresh());
	}

	find(name) {
		return (this.frm.doc.calendar_exceptions || []).find((row) => row.name === name);
	}

	can_write() {
		return this.frm.has_perm("write") && frappe.user.has_role("System Manager");
	}

	async refresh() {
		const request = ++this.request;
		this.render();
		try {
			const { message } = await frappe.call({
				method: "qota.governance.doctype.institutional_settings.institutional_settings.calendar_context",
				type: "GET",
			});
			if (request !== this.request) return;
			this.today = message.today;
			this.render();
		} catch (error) {
			if (request !== this.request) return;
			this.today = null;
			this.render(__("Unable to load the institutional calendar date. Reload the form."));
		}
	}

	static upcoming(doc, today) {
		return (doc.calendar_exceptions || []).filter((row) => row.exception_date >= today)
			.slice().sort((a, b) => a.exception_date.localeCompare(b.exception_date));
	}

	static format_date(day) {
		return String(day).split("-").reverse().join("/");
	}

	render(error) {
		const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
		const writable = this.can_write();
		const menu = writable ? `<div class="dropdown">
			<button type="button" class="btn btn-default btn-sm dropdown-toggle" data-toggle="dropdown"
				aria-haspopup="true" aria-expanded="false">${escape(__("Register exception"))}</button>
			<div class="dropdown-menu dropdown-menu-right">${OfficeCalendarEditor.types.map((type) =>
				`<button type="button" class="dropdown-item" data-register="${escape(type.value)}">${escape(__(type.action))}</button>`).join("")}</div>
		</div>` : "";
		let content;
		if (!this.today) {
			content = `<p class="text-muted" role="status">${escape(error || __("Loading calendar exceptions…"))}</p>`;
		} else {
			const rows = OfficeCalendarEditor.upcoming(this.frm.doc, this.today);
			content = rows.length ? `<div class="table-responsive"><table class="table table-bordered table-sm mb-0">
				<thead><tr>${["Date", "Type", "Hours", "Actions"].map((label) => `<th scope="col">${escape(__(label))}</th>`).join("")}</tr></thead>
				<tbody>${rows.map((row) => {
					const type = OfficeCalendarEditor.types.find((type) => type.value === row.exception_type);
					const intervals = (this.frm.doc.exception_hours || []).filter((slot) => slot.exception_date === row.exception_date);
					const hours = row.day_status === "Closed" ? __("Closed all day") : intervals.map((slot) =>
						`${String(slot.start_time).split(":").map((part) => part.padStart(2, "0")).slice(0, 2).join(":")}–${String(slot.end_time).split(":").map((part) => part.padStart(2, "0")).slice(0, 2).join(":")}`).join("; ");
					return `<tr><td class="text-nowrap">${escape(OfficeCalendarEditor.format_date(row.exception_date))}</td>
						<td>${escape(__(type ? type.label : row.exception_type))}</td><td class="text-nowrap">${escape(hours)}</td>
						<td class="text-nowrap">${writable ? `<button type="button" class="btn btn-default btn-xs" data-edit="${escape(row.name)}"
							aria-label="${escape(__("Edit exception on {0}", [OfficeCalendarEditor.format_date(row.exception_date)]))}">${escape(__("Edit"))}</button>
							<button type="button" class="btn btn-default btn-xs" data-remove="${escape(row.name)}"
							aria-label="${escape(__("Delete exception on {0}", [OfficeCalendarEditor.format_date(row.exception_date)]))}">${escape(__("Delete"))}</button>` : ""}</td></tr>`;
				}).join("")}</tbody></table></div>` : `<p class="text-muted mb-0">${escape(__("No upcoming exceptions registered."))}</p>`;
		}
		this.$wrapper.html(`<div class="mb-3">
			<div class="d-flex flex-wrap align-items-center justify-content-between mb-3">
				<h5 class="mb-2">${escape(__("Calendar exceptions"))}</h5>${menu}</div>
			<p class="text-muted small">${escape(__("Calendar dates use America/Tegucigalpa. Save the form to apply changes."))}</p>
			${this.frm.is_dirty() ? `<p class="text-warning small" role="status">${escape(__("Changes pending save"))}</p>` : ""}
			${content}</div>`);
	}

	open_dialog(kind, row) {
		if (!this.can_write()) return;
		const type = OfficeCalendarEditor.types.find((type) => type.value === kind);
		if (!type) return;
		const document = this.frm.doc;
		const interval = row && (document.exception_hours || []).find((slot) => slot.exception_date === row.exception_date);
		const fields = [{ fieldname: "exception_date", fieldtype: "Date", reqd: 1,
			label: __(kind === "Holiday" ? "Holiday Date" : "Date"), default: row?.exception_date }];
		if (kind === "Exceptional Hours") {
			fields.push(
				{ fieldname: "start_time", fieldtype: "Time", label: __("Opening Time"), reqd: 1, default: interval?.start_time },
				{ fieldname: "end_time", fieldtype: "Time", label: __("Closing Time"), reqd: 1, default: interval?.end_time },
			);
		}
		if (kind !== "Holiday") {
			fields.push({ fieldname: "internal_reason", fieldtype: "Small Text", label: __("Exception Reason"), reqd: 1,
				description: __("Internal administrative information. Never published."), default: row?.internal_reason });
		}
		let applying = false;
		const dialog = new frappe.ui.Dialog({
			title: row ? __("Edit {0}", [__(type.label)]) : __(type.action), fields,
			primary_action_label: __(row ? "Apply changes" : "Add exception"),
			primary_action: async (values) => {
				if (applying) return;
				if (this.frm.doc !== document || row && this.find(row.name) !== row) {
					frappe.throw(__("The form changed. Close this dialog and reopen the exception."));
				}
				applying = true;
				dialog.disable_primary_action();
				try {
					await this.apply(kind, values, row);
					dialog.hide();
				} finally {
					applying = false;
					dialog.enable_primary_action();
				}
			},
		});
		dialog.show();
	}

	remove_intervals(day) {
		(this.frm.doc.exception_hours || []).filter((slot) => slot.exception_date === day)
			.forEach((slot) => frappe.model.clear_doc(slot.doctype, slot.name));
	}

	async apply(kind, values, row) {
		if (!this.can_write()) return;
		const { exception, interval } = OfficeCalendarEditor.normalize(kind, values);
		if ((this.frm.doc.calendar_exceptions || []).some((other) => other !== row && other.exception_date === exception.exception_date)) {
			frappe.throw(__("Only one calendar exception is allowed per date."));
		}
		if (row) {
			const old_date = row.exception_date;
			await frappe.model.set_value(row.doctype, row.name, exception);
			this.remove_intervals(old_date);
		} else {
			this.frm.add_child("calendar_exceptions", exception);
		}
		if (interval) this.frm.add_child("exception_hours", interval);
		this.changed();
	}

	confirm_remove(row) {
		if (!this.can_write()) return;
		const document = this.frm.doc;
		const label = frappe.utils.escape_html(OfficeCalendarEditor.format_date(row.exception_date));
		frappe.confirm(__("Delete the calendar exception on {0}?", [label]), () => {
			if (this.frm.doc !== document || this.find(row.name) !== row) return;
			this.remove_intervals(row.exception_date);
			frappe.model.clear_doc(row.doctype, row.name);
			this.changed();
		});
	}

	changed() {
		for (const field of ["calendar_exceptions", "exception_hours"]) {
			(this.frm.doc[field] ||= []).sort((a, b) => a.exception_date.localeCompare(b.exception_date));
			this.frm.doc[field].forEach((row, index) => { row.idx = index + 1; });
		}
		this.frm.dirty();
		for (const field of ["calendar_exceptions", "exception_hours"]) {
			this.frm.refresh_field(field);
		}
		this.refresh();
	}
};
