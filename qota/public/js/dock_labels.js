// Dock item titles are stored as source text and drawn as-is. Translate only the
// label on screen. The stored title stays unchanged, so saving the dock does not
// write the translated words back into the record.
function translate_dock_item_labels() {
	const Dock = frappe.ui && frappe.ui.Dock;
	if (!Dock || Dock.prototype._qota_translates_labels) return;

	const render_item = Dock.prototype.make_dock_item;
	Dock.prototype.make_dock_item = function (entry) {
		if (!entry || !entry.label) return render_item.call(this, entry);
		const label = __(entry.label);
		if (!label || label === entry.label) return render_item.call(this, entry);
		return render_item.call(this, Object.assign({}, entry, { label }));
	};
	Dock.prototype._qota_translates_labels = true;
}

translate_dock_item_labels();
