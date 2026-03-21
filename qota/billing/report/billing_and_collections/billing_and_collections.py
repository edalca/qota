# Copyright (c) 2026, Edwin Carrillo and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Period"), "fieldname": "period", "fieldtype": "Data", "width": 100},
		{"label": _("Billed Amount"), "fieldname": "billed", "fieldtype": "Currency", "width": 120},
		{"label": _("Regular Payments"), "fieldname": "regular_paid", "fieldtype": "Currency", "width": 130},
		{"label": _("Applied Advances"), "fieldname": "advances_paid", "fieldtype": "Currency", "width": 130},
		{"label": _("Total Collected"), "fieldname": "total_collected", "fieldtype": "Currency", "width": 130},
		{"label": _("Pending Balance"), "fieldname": "pending", "fieldtype": "Currency", "width": 130},
		{"label": _("Efficiency %"), "fieldname": "efficiency", "fieldtype": "Percent", "width": 100},
	]


def get_data(filters):
	"""Return billing and collection metrics aggregated by billing period.

	Advances are identified when a payment was made before the corresponding
	Debt Ledger Entry was created, or when no ledger entry is linked.

	Args:
		filters (dict): Report filters (e.g., fiscal_year).

	Returns:
		list: Chronologically sorted list of metrics per period.
	"""
	ledgers = _get_ledger_entries(filters)
	payments = _get_payment_items(filters)

	report_map = {}

	for dle in ledgers:
		period = dle.billing_period
		if period not in report_map:
			report_map[period] = _create_empty_period(period)
		report_map[period]["billed"] += dle.amount
		report_map[period]["ledger_dates"][dle.name] = dle.creation

	for pay in payments:
		period = pay.billing_period
		if period not in report_map:
			report_map[period] = _create_empty_period(period)

		row = report_map[period]
		dle_creation = row["ledger_dates"].get(pay.debt_ledger_entry)
		is_advance = not pay.debt_ledger_entry or (dle_creation and pay.payment_date < dle_creation)

		if is_advance:
			row["advances_paid"] += pay.amount
		else:
			row["regular_paid"] += pay.amount

		row["total_collected"] += pay.amount

	sorted_periods = sorted(report_map.keys(), key=lambda x: (x.split("-")[1], x.split("-")[0]))

	final_data = []
	for p in sorted_periods:
		row = report_map[p]
		row["pending"] = max(0, row["billed"] - row["total_collected"])

		if row["billed"] > 0:
			row["efficiency"] = (row["total_collected"] / row["billed"]) * 100
		elif row["total_collected"] > 0:
			row["efficiency"] = 100

		mm, yyyy = p.split("-")
		row["period"] = f"{yyyy}-{mm}"
		row.pop("ledger_dates")
		final_data.append(row)

	return final_data


def _get_ledger_entries(filters):
	"""Return Debt Ledger Entry records, optionally filtered by fiscal year."""
	dle_filters = {}
	if filters.get("fiscal_year"):
		year = filters.get("fiscal_year")
		dle_filters["creation"] = ["between", [f"{year}-01-01", f"{year}-12-31 23:59:59"]]

	return frappe.get_all(
		"Debt Ledger Entry",
		filters=dle_filters,
		fields=["name", "billing_period", "amount", "paid_amount", "outstanding_amount", "creation"],
	)


def _get_payment_items(filters):
	"""Return Payment Receipt Item records with their payment date, optionally filtered by fiscal year."""
	receipt_filters = {"docstatus": 1}
	if filters.get("fiscal_year"):
		year = filters.get("fiscal_year")
		receipt_filters["payment_date"] = ["between", [f"{year}-01-01", f"{year}-12-31"]]

	receipts = frappe.get_all(
		"Payment Receipt",
		filters=receipt_filters,
		fields=["name", "payment_date"],
	)
	if not receipts:
		return []

	receipt_date = {r.name: r.payment_date for r in receipts}
	items = frappe.get_all(
		"Payment Receipt Item",
		filters={"parent": ["in", list(receipt_date)]},
		fields=["parent", "amount", "debt_ledger_entry", "billing_period"],
	)
	for item in items:
		item["payment_date"] = receipt_date[item.parent]
	return items


def _create_empty_period(period):
	"""Return a zeroed-out metrics dict for a new billing period."""
	return {
		"period": period,
		"billed": 0.0,
		"regular_paid": 0.0,
		"advances_paid": 0.0,
		"total_collected": 0.0,
		"pending": 0.0,
		"efficiency": 0.0,
		"ledger_dates": {},
	}
