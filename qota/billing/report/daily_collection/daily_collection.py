# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, flt


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart_data(data)
	report_summary = get_report_summary(data)

	return columns, data, None, chart, report_summary


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "payment_date", "fieldtype": "Datetime", "width": 160},
		{
			"label": _("Receipt"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Payment Receipt",
			"width": 120,
		},
		{"label": _("Subscriber"), "fieldname": "full_name", "fieldtype": "Data", "width": 180},
		{"label": _("Mode of Payment"), "fieldname": "mode_of_payment", "fieldtype": "Data", "width": 130},
		{"label": _("Reference No."), "fieldname": "reference_no", "fieldtype": "Data", "width": 120},
		{"label": _("Collected Amount"), "fieldname": "total_to_pay", "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	"""Return submitted Payment Receipt rows matching the given filters."""
	query_filters = [["docstatus", "=", 1]]

	if filters.get("from_date"):
		query_filters.append(["payment_date", ">=", filters.get("from_date")])
	if filters.get("to_date"):
		query_filters.append(["payment_date", "<", add_days(filters.get("to_date"), 1)])
	if filters.get("mode_of_payment"):
		query_filters.append(["mode_of_payment", "=", filters.get("mode_of_payment")])

	rows = frappe.get_all(
		"Payment Receipt",
		filters=query_filters,
		fields=["payment_date", "name", "full_name", "mode_of_payment", "reference_no", "total_to_pay"],
		order_by="payment_date asc",
	)
	TRANSLATIONS = {
		"Cash": _("Cash"),
		"Bank Transfer": _("Bank Transfer"),
		"Check": _("Check"),
		"Credit Card": _("Credit Card"),
	}

	for row in rows:
		row["mode_of_payment"] = TRANSLATIONS.get(row["mode_of_payment"], row["mode_of_payment"])

	return rows


def get_chart_data(data):
	"""Return a percentage chart showing collection distribution by payment mode."""
	if not data:
		return None

	mode_totals = {}
	for d in data:
		mode = d.get("mode_of_payment")
		mode_totals[mode] = mode_totals.get(mode, 0) + flt(d.get("total_to_pay"))

	return {
		"data": {"labels": list(mode_totals.keys()), "datasets": [{"values": list(mode_totals.values())}]},
		"type": "percentage",
	}


def get_report_summary(data):
	"""Return a summary card showing the total amount collected."""
	if not data:
		return None

	total_collected = sum(flt(d.get("total_to_pay")) for d in data)
	return [
		{
			"value": total_collected,
			"indicator": "Green",
			"label": _("Total Collected"),
			"datatype": "Currency",
		}
	]
