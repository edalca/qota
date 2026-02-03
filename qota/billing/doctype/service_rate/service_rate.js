// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Rate", {
	refresh: function (frm) {
		// Nada crítico al cargar, pero dejamos el bloque listo
	},

	min_consumption: function (frm) {
		// Si cambia el consumo mínimo incluido (ej. 15 m3),
		// sugerimos que el primer rango empiece desde ahí.
		if (frm.doc.ranges && frm.doc.ranges.length > 0) {
			let first_row = frm.doc.ranges[0];
			if (first_row.from_unit == 0 || !first_row.from_unit) {
				frappe.model.set_value(
					first_row.doctype,
					first_row.name,
					"from_unit",
					frm.doc.min_consumption,
				);
			}
		}
	},
});

frappe.ui.form.on("Service Rate Consumption Range", {
	// Cuando se agrega una nueva fila a la tabla de rangos
	ranges_add: function (frm, cdt, cdn) {
		let grid_rows = frm.doc.ranges;
		let new_row = locals[cdt][cdn];

		// Si es la primera fila, sugerimos empezar desde el Consumo Mínimo del encabezado
		if (grid_rows.length == 1) {
			frappe.model.set_value(cdt, cdn, "from_unit", frm.doc.min_consumption || 0);
		} else {
			// Si ya hay filas, buscamos la anterior para seguir la secuencia
			// El array grid_rows incluye la nueva fila al final, así que buscamos la penúltima
			let prev_row = grid_rows[grid_rows.length - 2];

			if (prev_row && prev_row.to_unit) {
				frappe.model.set_value(cdt, cdn, "from_unit", prev_row.to_unit);
			} else {
				frappe.msgprint({
					title: __("Validation Warning"),
					message: __("Please define the 'To (m3)' limit in the previous row first."),
					indicator: "orange",
				});
			}
		}
	},

	to_unit: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];

		// Validación visual rápida: To > From
		if (row.to_unit && row.from_unit && row.to_unit <= row.from_unit) {
			frappe.msgprint({
				title: __("Logic Error"),
				message: __("The 'To' limit ({0}) must be greater than the 'From' limit ({1}).", [
					row.to_unit,
					row.from_unit,
				]),
				indicator: "red",
			});
			frappe.model.set_value(cdt, cdn, "to_unit", ""); // Limpiar para obligar a corregir
		}
	},
});
