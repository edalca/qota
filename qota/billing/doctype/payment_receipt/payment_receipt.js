// Copyright (c) 2026, Edwin Carrillo and contributors
// For license information, please see license.txt

const MONTHS = [
	"January",
	"February",
	"March",
	"April",
	"May",
	"June",
	"July",
	"August",
	"September",
	"October",
	"November",
	"December",
];

frappe.ui.form.on("Payment Receipt", {
	setup: function (frm) {
		// Filtro: Solo contratos Activos (o Suspendidos para reconexión)
		frm.set_query("service_contract", function () {
			return {
				query: "qota.billing.doctype.service_contract.service_contract.contract_search",
				filters: { docstatus: 1 },
			};
		});
	},

	refresh: function (frm) {
		// Mostrar descripción de la propiedad (si existe la utilidad)
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}

		// --- ESTA ES LA LÍNEA MÁGICA ---
		// Esto oculta el botón "Add Row" de la tabla, pero permite que tus scripts sigan agregando filas.
		frm.set_df_property("payment_items", "cannot_add_rows", true);
		// -------------------------------

		// --- BOTONES DE HERRAMIENTAS (Solo en documentos nuevos) ---
		if (frm.is_new() && frm.doc.service_contract) {
			add_acctions_buttons(frm);
		}
	},

	premises: function (frm) {
		if (window.qota && qota.utils && qota.utils.set_premises_description) {
			qota.utils.set_premises_description(frm);
		}
	},

	service_contract: function (frm) {
		if (frm.is_new() && frm.doc.service_contract) {
			add_acctions_buttons(frm);
		}
		if (frm.doc.service_contract) {
			frappe.call({
				method: "qota.billing.doctype.payment_receipt.payment_receipt.get_payment_info",
				args: { contract: frm.doc.service_contract },
				callback: function (r) {
					if (r.message) {
						const data = r.message;

						// Llenar datos de cabecera
						frm.set_value("current_debt", data.current_debt);
						frm.set_value("monthly_rate_estimation", data.monthly_est);
						frm.set_value("is_reconnection_payment", data.is_reconnection);
						frm.set_value("reconnection_charge", data.reconnection_charge);

						// Guardar tarifa en caché para usarla en la tabla
						frm.monthly_rate_cache = data.monthly_est;

						// Calcular Total Sugerido (Deuda Ledger + Reconexión)
						let total_debt = data.current_debt;

						// Notificar si es reconexión
						if (data.is_reconnection) {
							total_debt += data.reconnection_charge;
							frappe.msgprint({
								title: __("Suspended Contract"),
								message: __(
									"Contract is Suspended. Reconnection charge of {0} applies.",
									[format_currency(data.reconnection_charge, frm.doc.currency)],
								),
								indicator: "orange",
							});
						}

						// Asignar valores iniciales
						if (total_debt > 0) {
							frm.set_value("total_to_pay", total_debt);
							// Sugerir pago total si la tabla está vacía
							if (
								frm.is_new() &&
								(!frm.doc.payment_items || frm.doc.payment_items.length === 0)
							) {
								frm.set_value("amount_paid", total_debt);
							}
						} else {
							frm.set_value("total_to_pay", 0);
							frappe.msgprint(
								__("Subscriber currently has no debt registered on the Ledger."),
							);
							if (frm.is_new()) frm.set_value("amount_paid", 0);
						}

						// Disparar recálculo visual
						frm.trigger("amount_paid");
					}
				},
			});
		}
	},

	amount_paid: function (frm) {
		// --- PROYECCIÓN VISUAL DE SALDO ---
		let debt = frm.doc.current_debt || 0;
		let paid = frm.doc.amount_paid || 0;
		let reconn = frm.doc.is_reconnection_payment ? frm.doc.reconnection_charge || 0 : 0;

		// Deuda Total = Lo que dice el Ledger + Cargo de Reconexión (que aun no está en ledger)
		let total_obligation = debt + reconn;
		let final_balance = total_obligation - paid;

		if (final_balance > 0.01) {
			frm.set_value(
				"resulting_balance",
				__("Remaining Debt: {0}", [format_currency(final_balance, frm.doc.currency)]),
			);
			frm.set_df_property(
				"resulting_balance",
				"description",
				"Subscriber will still owe money.",
			);
		} else if (final_balance < -0.01) {
			// Saldo a Favor
			let credit = Math.abs(final_balance);
			let monthly = frm.doc.monthly_rate_estimation || 1;
			let months_covered = (credit / monthly).toFixed(1);

			let message = __("CREDIT: {0} (Covers approx. {1} future months)", [
				format_currency(credit, frm.doc.currency),
				months_covered,
			]);
			frm.set_value("resulting_balance", message);
			frm.set_df_property(
				"resulting_balance",
				"description",
				"Positive balance for future bills.",
			);
		} else {
			// Cero
			frm.set_value("resulting_balance", __("Account Settled (Zero Balance)"));
			frm.set_df_property("resulting_balance", "description", "No debt remaining.");
		}
	},
});

// --- LÓGICA DE LA TABLA (Payment Receipt Item) ---

frappe.ui.form.on("Payment Receipt Item", {
	// Cuando se agrega una fila (manual o automática)
	payment_items_add: function (frm, cdt, cdn) {
		let rows = frm.doc.payment_items;

		// 1. Poner precio automáticamente
		if (frm.monthly_rate_cache) {
			frappe.model.set_value(cdt, cdn, "amount", frm.monthly_rate_cache);
		}

		// 2. INTELIGENCIA DE MESES
		// Si es la primera fila -> Poner Mes Actual
		if (rows.length === 1) {
			let today = new Date();
			let m_name = today.toLocaleString("en-US", { month: "long" });
			frappe.model.set_value(cdt, cdn, "month", m_name);
			frappe.model.set_value(cdt, cdn, "year", today.getFullYear());
		} else {
			// Si ya hay filas -> Poner Mes Siguiente al de la fila anterior
			let prev_row = rows[rows.length - 2];

			if (prev_row.month && prev_row.year) {
				let prev_idx = MONTHS.indexOf(prev_row.month);

				if (prev_idx !== -1) {
					let next_idx = prev_idx + 1;
					let next_year = prev_row.year;

					// Cambio de año (Diciembre -> Enero)
					if (next_idx > 11) {
						next_idx = 0;
						next_year = parseInt(prev_row.year) + 1;
					}

					frappe.model.set_value(cdt, cdn, "month", MONTHS[next_idx]);
					frappe.model.set_value(cdt, cdn, "year", next_year);
				}
			}
		}
	},

	payment_concept: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Si seleccionan Monthly Fee manual, poner precio
		if (row.payment_concept === "Monthly Fee" && frm.monthly_rate_cache) {
			frappe.model.set_value(cdt, cdn, "amount", frm.monthly_rate_cache);
		}
	},

	amount: function (frm, cdt, cdn) {
		calculate_total(frm);
	},

	payment_items_remove: function (frm) {
		calculate_total(frm);
	},
});

// --- FUNCIONES AUXILIARES ---

function calculate_total(frm) {
	let total = 0;
	let details = [];

	(frm.doc.payment_items || []).forEach((row) => {
		total += flt(row.amount);
		if (row.payment_concept === "Monthly Fee" && row.month) {
			details.push(`${row.month} ${row.year}`);
		} else {
			details.push(row.payment_concept);
		}
	});

	// Actualizar Total a Pagar
	if (total > 0) {
		frm.set_value("amount_paid", total);
	}

	// Actualizar Remarks Automáticamente
	if (details.length > 0) {
		let note = "Payment for: " + details.join(", ");
		frm.set_value("remarks", note);
	}
}

function load_pending_debt(frm) {
	if (!frm.doc.service_contract) {
		frappe.msgprint(__("Please select a contract first."));
		return;
	}

	// Nota: Cambié el nombre del método a 'get_pending_debts'
	frappe.call({
		method: "qota.billing.doctype.payment_receipt.payment_receipt.get_pending_debts",
		args: { contract: frm.doc.service_contract },
		freeze: true,
		freeze_message: __("Checking Ledger..."),
		callback: function (r) {
			if (r.message && r.message.length > 0) {
				frm.clear_table("payment_items");

				r.message.forEach((d) => {
					let row = frm.add_child("payment_items");

					row.payment_concept = d.payment_concept;
					row.amount = d.amount;

					// Solo llenar mes/año si vienen del servidor
					if (d.month) row.month = d.month;
					if (d.year) row.year = d.year;

					// Si es un cargo especial (Conexión, Multa), poner la nota
					if (d.description) row.description = d.description;
				});

				frm.refresh_field("payment_items");
				calculate_total(frm);

				frappe.msgprint({
					title: __("Debt Loaded"),
					message: __("Added {0} pending items (Bills & Fees).", [r.message.length]),
					indicator: "green",
				});
			} else {
				frappe.msgprint({
					title: __("Up to Date"),
					message: __("No pending debt found in the Ledger."),
					indicator: "blue",
				});
			}
		},
	});
}

function prompt_for_months(frm) {
	if (!frm.monthly_rate_cache) {
		frappe.msgprint(__("Please select a contract first."));
		return;
	}

	// Ventana emergente para pedir cantidad
	frappe.prompt(
		[
			{
				label: "Number of Months to Pay",
				fieldname: "qty",
				fieldtype: "Int",
				default: 1,
				reqd: 1,
			},
		],
		(values) => {
			add_next_months(frm, values.qty);
		},
		"Pay Future Months",
		"Add",
	);
}

function add_next_months(frm, count) {
	if (!frm.doc.service_contract) return;

	// 1. Verificar si ya hay filas en la tabla actual
	// Si la tabla YA tiene filas, seguimos la lógica visual (siguiente a la última fila)
	let rows = frm.doc.payment_items || [];
	if (rows.length > 0) {
		let last_row = rows[rows.length - 1];
		let m_idx = MONTHS.indexOf(last_row.month);
		let start_date = new Date(last_row.year, m_idx + 1, 1);
		generate_rows(frm, start_date, count);
	} else {
		// 2. Si la tabla está VACÍA, preguntamos al servidor: "¿Cuál es el siguiente mes que toca?"
		frappe.call({
			method: "qota.billing.doctype.payment_receipt.payment_receipt.get_next_payable_month",
			args: { contract: frm.doc.service_contract },
			freeze: true,
			callback: function (r) {
				if (r.message) {
					let d = r.message;
					// El servidor nos devuelve el próximo mes libre
					let start_date = new Date(d.year, d.month_idx, 1);
					generate_rows(frm, start_date, count);
				}
			},
		});
	}
}

// Función auxiliar para no repetir código
function generate_rows(frm, start_date, count) {
	let current_month_idx = start_date.getMonth();
	let current_year = start_date.getFullYear();

	for (let i = 0; i < count; i++) {
		let target_date = new Date(current_year, current_month_idx + i, 1);
		let m_name = target_date.toLocaleString("en-US", { month: "long" });

		let row = frm.add_child("payment_items");
		row.payment_concept = "Monthly Fee";
		row.month = m_name;
		row.year = target_date.getFullYear();
		row.amount = frm.monthly_rate_cache;
	}
	frm.refresh_field("payment_items");
	calculate_total(frm);
}

function add_acctions_buttons(frm) {
	if (frm.is_new() && frm.doc.service_contract) {
		// 1. CARGAR DEUDA PENDIENTE (Meses pasados no pagados)
		frm.add_custom_button(
			__("Load Pending Debt"),
			function () {
				load_pending_debt(frm);
			},
			__("Tools"),
		);

		// 2. ADELANTAR PAGOS (Meses futuros)
		frm.add_custom_button(
			__("Pay Multiple Months..."),
			function () {
				prompt_for_months(frm);
			},
			__("Tools"),
		);

		// 3. VER ESTADO DE CUENTA (Semáforo visual)
		frm.add_custom_button(
			__("View Account Status"),
			function () {
				show_status_dialog(frm);
			},
			__("View"),
		);
	}
}
function show_status_dialog(frm) {
	let year = new Date().getFullYear();

	frappe.call({
		method: "qota.billing.doctype.payment_receipt.payment_receipt.get_account_status",
		args: {
			contract: frm.doc.service_contract,
			year: year,
		},
		callback: function (r) {
			if (r.message) {
				let data = r.message;

				// Construir HTML de la tabla
				let html = `
                <table class="table table-bordered table-condensed">
                    <thead style="background-color: #f0f4f7;">
                        <tr>
                            <th>Month</th>
                            <th class="text-right">Billed</th>
                            <th class="text-right">Paid</th>
                            <th class="text-center">Status</th>
                        </tr>
                    </thead>
                    <tbody>`;

				let has_data = false;
				data.forEach((row) => {
					// Mostrar solo si hay movimiento
					if (row.bill > 0 || row.paid > 0) {
						has_data = true;

						// Color del badge
						let badge_class = "badge-gray";
						if (row.color === "green") badge_class = "badge-success"; // Pagado
						if (row.color === "red") badge_class = "badge-danger"; // Deuda
						if (row.color === "blue") badge_class = "badge-primary"; // Adelantado

						html += `
                        <tr>
                            <td><b>${row.month}</b></td>
                            <td class="text-right">${format_currency(row.bill, frm.doc.currency)}</td>
                            <td class="text-right">${format_currency(row.paid, frm.doc.currency)}</td>
                            <td class="text-center">
                                <span class="badge ${badge_class}">${row.status}</span>
                            </td>
                        </tr>`;
					}
				});

				if (!has_data) {
					html += `<tr><td colspan="4" class="text-center text-muted">No records for ${year}</td></tr>`;
				}

				html += `</tbody></table>`;

				let d = new frappe.ui.Dialog({
					title: `Account Status ${year}`,
					fields: [{ fieldtype: "HTML", options: html }],
					primary_action_label: "Close",
					primary_action: () => d.hide(),
				});
				d.show();
			}
		},
	});
}
